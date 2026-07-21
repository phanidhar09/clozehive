"""Unit tests for hybrid retrieval — BM25 lexical retriever, RRF fusion, and the
fashion_rag_service wiring that fuses the two.

All deterministic: no DB, no OpenAI. The lexical retriever and fusion are pure;
the service test stubs the embedding + pgvector calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.rag.fusion import reciprocal_rank_fusion
from app.rag.lexical import build_lexical_index

# ── Fixtures ──────────────────────────────────────────────────────────────────

_CORPUS = [
    {"title": "Natural Fibers Guide", "content": "Linen and wool breathe well in summer.",
     "category": "fabric", "tags": ["linen", "wool"], "occasion": None, "season": None},
    {"title": "Denim Styling", "content": "How to wear jeans for any occasion.",
     "category": "styling", "tags": ["denim", "jeans"], "occasion": None, "season": None},
    {"title": "Wedding Guest Guide", "content": "What to wear to a wedding as a guest.",
     "category": "occasion", "tags": ["wedding"], "occasion": "wedding", "season": None},
    {"title": "Rainy Weather Strategies", "content": "Stay dry with a waterproof jacket.",
     "category": "weather", "tags": ["rain", "waterproof"], "occasion": None, "season": None},
]


@pytest.fixture
def index():
    return build_lexical_index(_CORPUS)


# ── BM25 lexical retriever ────────────────────────────────────────────────────

def test_lexical_exact_term_ranks_first(index):
    """An exact fabric term should surface its document at the top."""
    results = index.search("linen wool", limit=3)
    assert results
    assert results[0]["title"] == "Natural Fibers Guide"
    assert results[0]["lexical_score"] > 0


def test_lexical_no_overlap_returns_empty(index):
    """A query sharing no tokens with any document returns nothing."""
    assert index.search("spaceship rocket propulsion", limit=5) == []


def test_lexical_respects_limit(index):
    results = index.search("wear occasion guide", limit=1)
    assert len(results) <= 1


def test_lexical_category_filter(index):
    """Category filter restricts scoring to that category."""
    results = index.search("wedding jeans linen rain", limit=5, category="fabric")
    assert all(r["category"] == "fabric" for r in results)
    assert results and results[0]["title"] == "Natural Fibers Guide"


def test_lexical_empty_corpus_is_safe():
    idx = build_lexical_index([])
    assert idx.search("anything", limit=5) == []


def test_lexical_ignores_stopwords(index):
    """A query of only stopwords scores nothing."""
    assert index.search("the and of to in", limit=5) == []


# ── RRF fusion ────────────────────────────────────────────────────────────────

def _key(item):
    return item["title"].lower()


def test_rrf_rewards_documents_in_both_lists():
    """A doc ranked in both retrievers beats a doc ranked highly in only one."""
    vector = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    lexical = [{"title": "C"}, {"title": "D"}, {"title": "A"}]
    fused = reciprocal_rank_fusion([vector, lexical], key=_key)
    order = [k for k, _ in fused]
    # A appears in both (ranks 1 and 3); it should outrank B (only vector rank 2).
    assert order.index("a") < order.index("b")
    assert order.index("c") < order.index("b")


def test_rrf_single_list_preserves_order():
    single = [{"title": "X"}, {"title": "Y"}, {"title": "Z"}]
    fused = reciprocal_rank_fusion([single], key=_key)
    assert [k for k, _ in fused] == ["x", "y", "z"]


def test_rrf_empty_input():
    assert reciprocal_rank_fusion([[], []], key=_key) == []


def test_rrf_weights_shift_ranking():
    vector = [{"title": "A"}, {"title": "B"}]
    lexical = [{"title": "B"}, {"title": "A"}]
    # Weight lexical far higher — B (lexical rank 1) should win.
    fused = reciprocal_rank_fusion([vector, lexical], key=_key, weights=[0.1, 10.0])
    assert fused[0][0] == "b"


def test_rrf_weights_length_mismatch_raises():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[{"title": "A"}]], key=_key, weights=[1.0, 2.0])


# ── Hybrid wiring in fashion_rag_service ──────────────────────────────────────

@pytest.mark.asyncio
async def test_hybrid_recovers_lexical_only_match():
    """When the vector half misses a doc whose exact term is in the query, the
    lexical half + fusion should still surface it."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    mock_session = AsyncMock()

    with patch.object(svc, "ensure_seeded", new=AsyncMock(return_value=None)), patch.object(
        svc, "generate_text_embedding", new=AsyncMock(return_value=[0.0] * 1536)
    ), patch.object(
        # Vector search returns an unrelated doc — the exact-term doc is missing.
        svc, "pgvector_cosine_search",
        new=AsyncMock(return_value=[
            {"id": "1", "title": "Color Matching Fundamentals",
             "content": "colors", "category": "color", "season": None,
             "occasion": None, "similarity_score": 0.71},
        ]),
    ):
        docs = await svc.search_fashion_knowledge(
            mock_session, "styling advice for denim jeans", limit=5
        )

    titles = [d["title"] for d in docs]
    # The denim doc, absent from the vector list, is recovered by BM25 + fusion.
    assert "Denim Styling and Versatility Guide" in titles


@pytest.mark.asyncio
async def test_hybrid_disabled_falls_back_to_vector_only(monkeypatch):
    """With rag_hybrid_enabled=False, only vector results flow through."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    settings = svc.get_settings()
    monkeypatch.setattr(settings, "rag_hybrid_enabled", False)

    mock_session = AsyncMock()
    with patch.object(svc, "ensure_seeded", new=AsyncMock(return_value=None)), patch.object(
        svc, "generate_text_embedding", new=AsyncMock(return_value=[0.0] * 1536)
    ), patch.object(
        svc, "pgvector_cosine_search",
        new=AsyncMock(return_value=[
            {"id": "1", "title": "Color Matching Fundamentals", "content": "colors",
             "category": "color", "season": None, "occasion": None, "similarity_score": 0.71},
        ]),
    ):
        docs = await svc.search_fashion_knowledge(mock_session, "denim jeans", limit=5)

    titles = [d["title"] for d in docs]
    assert titles == ["Color Matching Fundamentals"]
    assert "Denim Styling and Versatility Guide" not in titles
