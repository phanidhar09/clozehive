"""Unit tests for the gender metadata pre-filter (app/rag/metadata_filter.py) and
its wiring into fashion_rag_service.

Deterministic: no DB, no OpenAI. The filter helpers are pure; the service test
stubs the embedding + pgvector calls and asserts the pre-filter is applied to both
halves of hybrid retrieval before ranking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.rag.metadata_filter import (
    canonical_gender,
    filter_by_gender,
    gender_allows,
    gender_of_row,
)

# ── canonical_gender ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("men", "men"),
        ("Male", "men"),
        ("MENSWEAR", "men"),
        ("women", "women"),
        ("Female", "women"),
        ("unisex", None),  # neutral → no binary signal
        ("non-binary", None),
        ("", None),
        (None, None),
        ("   Men  ", "men"),
    ],
)
def test_canonical_gender(value, expected):
    assert canonical_gender(value) == expected


# ── gender_allows ─────────────────────────────────────────────────────────────


def test_gender_allows_no_target_passes_everything():
    assert gender_allows("men", None) is True
    assert gender_allows("women", None) is True


def test_gender_allows_neutral_docs_serve_everyone():
    for neutral in ("unisex", None, "prefer_not_to_say"):
        assert gender_allows(neutral, "men") is True
        assert gender_allows(neutral, "women") is True


def test_gender_allows_matches_and_excludes():
    assert gender_allows("men", "men") is True
    assert gender_allows("women", "women") is True
    assert gender_allows("men", "women") is False
    assert gender_allows("women", "men") is False


# ── gender_of_row (both shapes) ───────────────────────────────────────────────


def test_gender_of_row_top_level():
    assert gender_of_row({"gender": "women"}) == "women"


def test_gender_of_row_nested_in_tags_jsonb():
    assert gender_of_row({"tags": {"gender": "men", "tags": ["suit"]}}) == "men"


def test_gender_of_row_absent():
    assert gender_of_row({"title": "x", "tags": ["casual"]}) is None
    assert gender_of_row({}) is None


# ── filter_by_gender ──────────────────────────────────────────────────────────

_DOCS = [
    {"title": "Menswear Tailoring", "gender": "men"},
    {"title": "Womenswear Draping", "gender": "women"},
    {"title": "Universal Color Theory", "gender": "unisex"},
    {"title": "Untagged Basics"},  # no gender → neutral
]


def test_filter_by_gender_none_is_noop():
    assert filter_by_gender(_DOCS, None) == _DOCS


def test_filter_by_gender_keeps_target_plus_neutral():
    titles = [d["title"] for d in filter_by_gender(_DOCS, "women")]
    assert "Womenswear Draping" in titles
    assert "Universal Color Theory" in titles  # unisex kept
    assert "Untagged Basics" in titles  # neutral kept
    assert "Menswear Tailoring" not in titles  # wrong audience dropped


def test_filter_by_gender_preserves_order():
    out = filter_by_gender(_DOCS, "men")
    assert [d["title"] for d in out] == ["Menswear Tailoring", "Universal Color Theory", "Untagged Basics"]


# ── Service wiring: pre-filter applied to both halves before ranking ──────────


@pytest.mark.asyncio
async def test_search_passes_tags_gender_to_dense_and_filters_lexical():
    """A women's-audience query must (a) push tags_gender='women' into the SQL
    dense pre-filter and (b) drop a men-only lexical hit before fusion."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    mock_session = AsyncMock()
    pgvector_mock = AsyncMock(
        return_value=[
            {"id": "1", "title": "Color Matching Fundamentals", "content": "colors",
             "category": "color", "season": None, "occasion": None, "similarity_score": 0.71},
        ]
    )
    # Lexical returns one women's doc and one men-only doc; the men doc must be
    # filtered out before it can reach fusion/rerank.
    lexical_mock = [
        {"id": "", "title": "Womens Evening Looks", "content": "gowns", "category": "occasion",
         "season": None, "occasion": None, "gender": "women", "lexical_score": 2.0},
        {"id": "", "title": "Mens Black Tie", "content": "tuxedo", "category": "occasion",
         "season": None, "occasion": None, "gender": "men", "lexical_score": 3.0},
    ]

    with patch.object(svc, "ensure_seeded", new=AsyncMock(return_value=None)), patch.object(
        svc, "generate_text_embedding", new=AsyncMock(return_value=[0.0] * 1536)
    ), patch.object(svc, "pgvector_cosine_search", new=pgvector_mock), patch.object(
        svc._LEXICAL_INDEX, "search", return_value=lexical_mock
    ):
        docs = await svc.search_fashion_knowledge(
            mock_session, "evening outfit ideas", limit=5, gender="female"
        )

    # (a) dense half received the canonicalised audience as a SQL pre-filter.
    assert pgvector_mock.await_args.kwargs["tags_gender"] == "women"
    # (b) the men-only lexical doc never made it into the fused output.
    titles = [d["title"] for d in docs]
    assert "Mens Black Tie" not in titles
    assert "Womens Evening Looks" in titles


@pytest.mark.asyncio
async def test_search_no_gender_leaves_retrieval_unfiltered():
    """Without a gender signal, tags_gender is None and nothing is dropped."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    mock_session = AsyncMock()
    pgvector_mock = AsyncMock(
        return_value=[
            {"id": "1", "title": "Color Matching Fundamentals", "content": "colors",
             "category": "color", "season": None, "occasion": None, "similarity_score": 0.71},
        ]
    )
    lexical_mock = [
        {"id": "", "title": "Mens Black Tie", "content": "tuxedo", "category": "occasion",
         "season": None, "occasion": None, "gender": "men", "lexical_score": 3.0},
    ]

    with patch.object(svc, "ensure_seeded", new=AsyncMock(return_value=None)), patch.object(
        svc, "generate_text_embedding", new=AsyncMock(return_value=[0.0] * 1536)
    ), patch.object(svc, "pgvector_cosine_search", new=pgvector_mock), patch.object(
        svc._LEXICAL_INDEX, "search", return_value=lexical_mock
    ):
        docs = await svc.search_fashion_knowledge(mock_session, "evening outfit ideas", limit=5)

    assert pgvector_mock.await_args.kwargs["tags_gender"] is None
    assert "Mens Black Tie" in [d["title"] for d in docs]  # not filtered


@pytest.mark.asyncio
async def test_prefilter_disabled_setting_is_inert(monkeypatch):
    """With rag_metadata_prefilter_enabled=False, a gender signal is ignored."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    settings = svc.get_settings()
    monkeypatch.setattr(settings, "rag_metadata_prefilter_enabled", False)

    mock_session = AsyncMock()
    pgvector_mock = AsyncMock(return_value=[])
    lexical_mock = [
        {"id": "", "title": "Mens Black Tie", "content": "tuxedo", "category": "occasion",
         "season": None, "occasion": None, "gender": "men", "lexical_score": 3.0},
    ]

    with patch.object(svc, "ensure_seeded", new=AsyncMock(return_value=None)), patch.object(
        svc, "generate_text_embedding", new=AsyncMock(return_value=[0.0] * 1536)
    ), patch.object(svc, "pgvector_cosine_search", new=pgvector_mock), patch.object(
        svc._LEXICAL_INDEX, "search", return_value=lexical_mock
    ):
        docs = await svc.search_fashion_knowledge(
            mock_session, "evening outfit ideas", limit=5, gender="female"
        )

    assert pgvector_mock.await_args.kwargs["tags_gender"] is None
    assert "Mens Black Tie" in [d["title"] for d in docs]  # disabled → not filtered


# ── Prompt wrapper: gender resolution from user_id (outfit-builder / chat paths) ─


@pytest.mark.asyncio
async def test_prompt_wrapper_resolves_gender_from_user_id():
    """get_fashion_context_for_prompt resolves the profile gender when only a
    user_id is supplied, and forwards it to the search (chat / outfit-builder wiring)."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    search_mock = AsyncMock(return_value=[])
    with patch(
        "app.api.v1.identity.services.style_profile_context.load_profile_gender",
        new=AsyncMock(return_value="female"),
    ), patch.object(svc, "search_fashion_knowledge", new=search_mock):
        await svc.get_fashion_context_for_prompt(AsyncMock(), "evening looks", user_id="u-1")

    assert search_mock.await_args.kwargs["gender"] == "female"


@pytest.mark.asyncio
async def test_prompt_wrapper_explicit_gender_wins_over_user_id():
    """An explicit gender short-circuits the profile lookup entirely."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    search_mock = AsyncMock(return_value=[])
    resolver = AsyncMock(return_value="male")
    with patch(
        "app.api.v1.identity.services.style_profile_context.load_profile_gender", new=resolver
    ), patch.object(svc, "search_fashion_knowledge", new=search_mock):
        await svc.get_fashion_context_for_prompt(
            AsyncMock(), "evening looks", gender="women", user_id="u-1"
        )

    resolver.assert_not_awaited()  # explicit gender means no profile query
    assert search_mock.await_args.kwargs["gender"] == "women"
