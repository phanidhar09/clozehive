"""Cross-encoder reranking wired into the closet-item and outfit-history paths.

Exercises retriever.retrieve_outfit_context and retrieve_similar_items over the
FAISS backend with the embedding call stubbed and the LLM reranker mocked, so
they're deterministic. Confirms the reranker reorders when enabled, is scoped to
the text-query case for closet items, and no-ops when disabled.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.rag import retriever
from app.rag.vector_store import (
    SOURCE_CLOSET_ITEM,
    SOURCE_OUTFIT_HISTORY,
    EmbeddingMeta,
    FAISSVectorStore,
)

USER = str(uuid.uuid4())


def _embedding(seed: int = 1) -> list[float]:
    import numpy as np

    v = np.random.default_rng(seed).random(1536).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


@pytest.fixture
def store() -> FAISSVectorStore:
    return FAISSVectorStore(index_dir=None)


def _enable_ce(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rag_cross_encoder_enabled", True)
    return settings


def _chat(payload: str) -> AsyncMock:
    return AsyncMock(return_value=payload)


# ── Outfit history ────────────────────────────────────────────────────────────


async def _seed_history(store, ids_occasions):
    for i, (rid, occ) in enumerate(ids_occasions):
        await store.upsert(
            meta=EmbeddingMeta(
                record_id=rid,
                source_type=SOURCE_OUTFIT_HISTORY,
                user_id=USER,
                occasion=[occ],
                payload={
                    "occasion": occ,
                    "weather_context": {"weather": "warm"},
                    "selected_item_ids": [],
                    "matching_score": 80,
                    "recommendation_text": f"Past {occ} outfit",
                    "improvement_tips": [],
                    "was_saved": False,
                    "was_worn": False,
                    "user_feedback": None,
                    "created_at": "2025-01-0%d" % (i + 1),
                },
            ),
            embedding=_embedding(seed=i + 1),
        )


@pytest.mark.asyncio
async def test_outfit_history_reranked_when_enabled(monkeypatch, store):
    _enable_ce(monkeypatch)
    await _seed_history(store, [("h-casual", "casual"), ("h-wedding", "wedding")])

    # Model ranks the 2nd history record above the 1st (ids are post-metadata-rerank order).
    payload = json.dumps({"scores": [{"id": 0, "score": 2}, {"id": 1, "score": 9}]})

    with (
        patch("app.rag.retriever.fashion_rag_service.search_fashion_knowledge", new=AsyncMock(return_value=[])),
        patch("app.rag.retriever.generate_text_embedding", new=AsyncMock(return_value=_embedding(seed=1))),
        patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat(payload)),
    ):
        result = await retriever.retrieve_outfit_context(
            AsyncMock(), user_id=USER, occasion="wedding", weather="warm", limit=5, store=store
        )

    hist = result["outfit_history"]
    assert len(hist) == 2
    # The record the model scored highest is now first, and carries a rerank_score.
    assert hist[0].get("rerank_score") == 9.0


@pytest.mark.asyncio
async def test_outfit_history_not_reranked_when_disabled(monkeypatch, store):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rag_cross_encoder_enabled", False)
    await _seed_history(store, [("h-1", "casual")])
    chat = AsyncMock()

    with (
        patch("app.rag.retriever.fashion_rag_service.search_fashion_knowledge", new=AsyncMock(return_value=[])),
        patch("app.rag.retriever.generate_text_embedding", new=AsyncMock(return_value=_embedding(seed=1))),
        patch("app.api.v1.intelligence.services.ai_service.chat", new=chat),
    ):
        result = await retriever.retrieve_outfit_context(
            AsyncMock(), user_id=USER, occasion="casual", limit=5, store=store
        )

    assert result["outfit_history"]
    assert "rerank_score" not in result["outfit_history"][0]
    chat.assert_not_called()


# ── Closet similar items ──────────────────────────────────────────────────────


async def _seed_items(store, items):
    for i, (rid, name, cat, color) in enumerate(items):
        await store.upsert(
            meta=EmbeddingMeta(
                record_id=rid,
                source_type=SOURCE_CLOSET_ITEM,
                user_id=USER,
                category=cat,
                color=color,
                payload={"name": name, "category": cat, "color": color, "brand": ""},
            ),
            embedding=_embedding(seed=i + 1),
        )


@pytest.mark.asyncio
async def test_closet_text_query_reranked(monkeypatch, store):
    _enable_ce(monkeypatch)
    await _seed_items(store, [("i-1", "Blue Shirt", "tops", "blue"), ("i-2", "Navy Blazer", "outerwear", "navy")])
    payload = json.dumps({"scores": [{"id": 0, "score": 1}, {"id": 1, "score": 10}]})

    with (
        patch("app.rag.retriever.generate_text_embedding", new=AsyncMock(return_value=_embedding(seed=1))),
        patch("app.core.embedding_service.generate_text_embedding", new=AsyncMock(return_value=_embedding(seed=1))),
        patch("app.api.v1.intelligence.services.ai_service.chat", new=_chat(payload)),
    ):
        result = await retriever.retrieve_similar_items(
            AsyncMock(), user_id=USER, query="a navy blazer", limit=5, store=store
        )

    assert result["query_type"] == "text_query"
    assert result["results"]
    assert result["results"][0].get("rerank_score") == 10.0


@pytest.mark.asyncio
async def test_closet_item_id_case_skips_reranker(monkeypatch, store):
    """Item-id similarity has no NL query, so the reranker must not run."""
    _enable_ce(monkeypatch)
    await _seed_items(store, [("i-src", "Blue Shirt", "tops", "blue"), ("i-2", "Sky Tee", "tops", "sky")])
    chat = AsyncMock()

    # Load the source item so the FAISS item-id branch builds a query embedding.
    from app.models.closet import ClosetItem

    src = ClosetItem(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        user_id=uuid.UUID(USER),
        name="Blue Shirt",
        category="tops",
        color="blue",
    )

    async def _fake_get(model, pk):
        return src

    mock_session = AsyncMock()
    mock_session.get = _fake_get

    with (
        patch("app.rag.retriever.generate_text_embedding", new=AsyncMock(return_value=_embedding(seed=1))),
        patch("app.core.embedding_service.generate_text_embedding", new=AsyncMock(return_value=_embedding(seed=1))),
        patch("app.api.v1.intelligence.services.ai_service.chat", new=chat),
    ):
        result = await retriever.retrieve_similar_items(
            mock_session, user_id=USER, closet_item_id="00000000-0000-0000-0000-0000000000aa", limit=5, store=store
        )

    assert result["query_type"] == "closet_item"
    chat.assert_not_called()  # no NL query → no rerank
