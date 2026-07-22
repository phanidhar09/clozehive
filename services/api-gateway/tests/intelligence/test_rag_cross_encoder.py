"""Unit tests for the LLM cross-encoder reranker.

The LLM call (ai_service.chat) is always mocked, so these are deterministic. They
pin the reranker's core contract: it reorders by model score, never drops a
document, and degrades to the input order on every failure mode.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.rag import cross_encoder


def _docs():
    return [
        {"title": "A", "content": "alpha"},
        {"title": "B", "content": "bravo"},
        {"title": "C", "content": "charlie"},
    ]


def _text_of(doc):
    return f"{doc['title']}. {doc['content']}"


def _enable(monkeypatch):
    settings = cross_encoder.get_settings()
    monkeypatch.setattr(settings, "rag_cross_encoder_enabled", True)
    return settings


def _chat_returning(payload: str) -> AsyncMock:
    return AsyncMock(return_value=payload)


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reorders_by_model_score(monkeypatch):
    _enable(monkeypatch)
    # Model says C is most relevant, then A, then B.
    payload = json.dumps({"scores": [{"id": 0, "score": 6}, {"id": 1, "score": 2}, {"id": 2, "score": 9}]})
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat_returning(payload)):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert [d["title"] for d in out] == ["C", "A", "B"]
    assert out[0]["rerank_score"] == 9.0


@pytest.mark.asyncio
async def test_only_top_n_reranked_tail_preserved(monkeypatch):
    _enable(monkeypatch)
    docs = [{"title": t, "content": t.lower()} for t in ["A", "B", "C", "D"]]
    # top_n=2 → only A,B are scored (B above A); C,D stay in original order after.
    payload = json.dumps({"scores": [{"id": 0, "score": 1}, {"id": 1, "score": 8}]})
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat_returning(payload)):
        out = await cross_encoder.rerank("q", docs, text_of=_text_of, top_n=2)
    assert [d["title"] for d in out] == ["B", "A", "C", "D"]


# ── Never drops documents ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_never_drops_unscored_documents(monkeypatch):
    _enable(monkeypatch)
    # Model only scores id 2 and includes a bogus out-of-range id — the others
    # must still survive, beneath the scored one, in their original order.
    payload = json.dumps({"scores": [{"id": 2, "score": 7}, {"id": 99, "score": 10}]})
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat_returning(payload)):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert {d["title"] for d in out} == {"A", "B", "C"}
    assert out[0]["title"] == "C"  # the only scored doc floats to the top
    assert [d["title"] for d in out[1:]] == ["A", "B"]  # unscored keep input order


# ── Failure modes all degrade to input order ─────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_json_returns_input_order(monkeypatch):
    _enable(monkeypatch)
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat_returning("not json at all")):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert [d["title"] for d in out] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_llm_exception_returns_input_order(monkeypatch):
    _enable(monkeypatch)
    with patch(
        "app.api.v1.intelligence.services.ai_service.chat",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert [d["title"] for d in out] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_empty_scores_object_returns_input_order(monkeypatch):
    _enable(monkeypatch)
    with patch(
        "app.api.v1.intelligence.services.ai_service.chat",
        new=_chat_returning(json.dumps({"scores": []})),
    ):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert [d["title"] for d in out] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_tolerates_code_fenced_json(monkeypatch):
    _enable(monkeypatch)
    fenced = "```json\n" + json.dumps({"scores": [{"id": 1, "score": 9}]}) + "\n```"
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat_returning(fenced)):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert out[0]["title"] == "B"


# ── Short-circuits (no LLM call) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disabled_is_noop_without_llm_call(monkeypatch):
    settings = cross_encoder.get_settings()
    monkeypatch.setattr(settings, "rag_cross_encoder_enabled", False)
    chat = AsyncMock()
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=chat):
        out = await cross_encoder.rerank("q", _docs(), text_of=_text_of)
    assert [d["title"] for d in out] == ["A", "B", "C"]
    chat.assert_not_called()


@pytest.mark.asyncio
async def test_single_doc_short_circuits(monkeypatch):
    _enable(monkeypatch)
    chat = AsyncMock()
    with patch("app.api.v1.intelligence.services.ai_service.chat", new=chat):
        out = await cross_encoder.rerank("q", [{"title": "A", "content": "a"}], text_of=_text_of)
    assert [d["title"] for d in out] == ["A"]
    chat.assert_not_called()


# ── Wiring: the stage runs inside search_fashion_knowledge ────────────────────

@pytest.mark.asyncio
async def test_search_fashion_knowledge_applies_cross_encoder(monkeypatch):
    """End-to-end: with the flag on, the final order reflects rerank scores."""
    from app.api.v1.intelligence.services import fashion_rag_service as svc

    settings = svc.get_settings()
    monkeypatch.setattr(settings, "rag_cross_encoder_enabled", True)
    # Disable hybrid so only the mocked vector rows reach the rerank stage — the
    # real BM25 index would otherwise fuse in live corpus docs and shift the ids.
    monkeypatch.setattr(settings, "rag_hybrid_enabled", False)
    mock_session = AsyncMock()

    vector_rows = [
        {"id": "1", "title": "Color Matching Fundamentals", "content": "colors",
         "category": "color", "season": None, "occasion": None, "similarity_score": 0.72},
        {"id": "2", "title": "Shoe Matching Rules", "content": "shoes",
         "category": "styling", "season": None, "occasion": None, "similarity_score": 0.70},
    ]
    # Model ranks the 2nd retrieved doc (Shoe Matching Rules, id 1) above the 1st.
    payload = json.dumps({"scores": [{"id": 0, "score": 2}, {"id": 1, "score": 9}]})

    with patch.object(svc, "ensure_seeded", new=AsyncMock(return_value=None)), patch.object(
        svc, "generate_text_embedding", new=AsyncMock(return_value=[0.0] * 1536)
    ), patch.object(
        svc, "pgvector_cosine_search", new=AsyncMock(return_value=vector_rows)
    ), patch(
        "app.api.v1.intelligence.services.ai_service.chat", new=_chat_returning(payload)
    ):
        docs = await svc.search_fashion_knowledge(mock_session, "which shoes go with this", limit=5)

    assert docs[0]["title"] == "Shoe Matching Rules"
    assert docs[0]["rerank_score"] == 9.0
