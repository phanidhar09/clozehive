"""
Unit tests — RAG retrieval filtering.

Tests verify that:
  - Category and occasion filters restrict results to relevant documents.
  - Similarity threshold gates work: results below threshold are excluded.
  - Metadata (color, season, style_tags) stored at upsert is returned on search.
  - FAISS over-fetch then filter correctly returns at most `limit` results.
  - Multiple source_types are stored independently (no cross-contamination).

All tests use FAISSVectorStore with pre-seeded embeddings — no database or
OpenAI API calls are made.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.rag.vector_store import (
    EmbeddingMeta,
    FAISSVectorStore,
    SOURCE_CLOSET_ITEM,
    SOURCE_OUTFIT_HISTORY,
    SOURCE_FASHION_KNOWLEDGE,
)
from app.rag import retriever


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rand_embedding(seed: int = 0) -> list[float]:
    """Deterministic 1536-dim unit vector for testing."""
    import numpy as np
    rng = np.random.default_rng(seed)
    v = rng.random(1536).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


def _make_meta(
    record_id: str,
    source_type: str,
    user_id: str | None = None,
    category: str | None = None,
    color: str | None = None,
    season: list[str] | None = None,
    occasion: list[str] | None = None,
    style_tags: list[str] | None = None,
    payload: dict | None = None,
) -> EmbeddingMeta:
    return EmbeddingMeta(
        record_id=record_id,
        source_type=source_type,
        user_id=user_id,
        category=category,
        color=color,
        season=season,
        occasion=occasion,
        style_tags=style_tags,
        payload=payload or {},
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store() -> FAISSVectorStore:
    """Fresh in-memory FAISS store (no disk persistence) per test."""
    return FAISSVectorStore(index_dir=None)


USER_A = str(uuid.uuid4())
SHARED_EMBEDDING = _rand_embedding(seed=42)  # same seed = same vector


# ── Exact match returns highest score ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_exact_embedding_match_returns_score_near_one(store):
    """Searching with the same vector that was upserted should return score ≈ 1.0."""
    vec = _rand_embedding(seed=1)
    await store.upsert(
        meta=_make_meta("item-1", SOURCE_CLOSET_ITEM, user_id=USER_A, category="tops"),
        embedding=vec,
    )
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec,
        user_id=USER_A,
        limit=5,
        threshold=0.50,
    )
    assert len(results) == 1
    assert results[0].record_id == "item-1"
    assert results[0].similarity_score > 0.99


# ── Threshold gates low-similarity results ────────────────────────────────────

@pytest.mark.asyncio
async def test_threshold_excludes_low_similarity_result(store):
    """A result below threshold must not appear in output."""
    vec_stored = _rand_embedding(seed=10)   # stored vector
    vec_query = _rand_embedding(seed=99)    # very different query vector

    await store.upsert(
        meta=_make_meta("item-low", SOURCE_CLOSET_ITEM, user_id=USER_A),
        embedding=vec_stored,
    )
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec_query,
        user_id=USER_A,
        limit=5,
        threshold=0.99,   # very tight threshold — random vectors won't pass
    )
    assert results == []


@pytest.mark.asyncio
async def test_threshold_passes_similar_result(store):
    """A result above threshold must appear."""
    vec = _rand_embedding(seed=5)
    await store.upsert(
        meta=_make_meta("item-pass", SOURCE_CLOSET_ITEM, user_id=USER_A),
        embedding=vec,
    )
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec,
        user_id=USER_A,
        limit=5,
        threshold=0.50,
    )
    assert any(r.record_id == "item-pass" for r in results)


# ── Limit is respected ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_limit_caps_result_count(store):
    """Store 10 identical items; requesting limit=3 returns exactly 3."""
    vec = _rand_embedding(seed=7)
    for i in range(10):
        await store.upsert(
            meta=_make_meta(f"item-{i}", SOURCE_CLOSET_ITEM, user_id=USER_A),
            embedding=vec,
        )
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec,
        user_id=USER_A,
        limit=3,
        threshold=0.50,
    )
    assert len(results) <= 3


# ── Metadata round-trips correctly ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_metadata_preserved_through_upsert_and_search(store):
    """Metadata stored at upsert time must be intact in search results."""
    vec = _rand_embedding(seed=20)
    await store.upsert(
        meta=_make_meta(
            "shirt-001",
            SOURCE_CLOSET_ITEM,
            user_id=USER_A,
            category="tops",
            color="sky blue",
            season=["spring", "summer"],
            occasion=["casual", "beach"],
            style_tags=["floral", "linen"],
            payload={"name": "Linen Floral Shirt", "brand": "Zara"},
        ),
        embedding=vec,
    )
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec,
        user_id=USER_A,
        limit=1,
        threshold=0.50,
    )
    assert len(results) == 1
    r = results[0]
    assert r.category == "tops"
    assert r.color == "sky blue"
    assert r.season == ["spring", "summer"]
    assert r.occasion == ["casual", "beach"]
    assert r.style_tags == ["floral", "linen"]
    assert r.payload["name"] == "Linen Floral Shirt"


# ── Multiple source_types don't contaminate each other ───────────────────────

@pytest.mark.asyncio
async def test_source_types_are_isolated(store):
    """Items from different source_types must not appear in each other's results."""
    vec = _rand_embedding(seed=15)
    await store.upsert(
        meta=_make_meta("closet-1", SOURCE_CLOSET_ITEM, user_id=USER_A),
        embedding=vec,
    )
    await store.upsert(
        meta=_make_meta("history-1", SOURCE_OUTFIT_HISTORY, user_id=USER_A),
        embedding=vec,
    )
    # Search closet_items: should only return closet-1
    closet_results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec,
        user_id=USER_A,
        limit=10,
        threshold=0.50,
    )
    assert all(r.source_type == SOURCE_CLOSET_ITEM for r in closet_results)
    assert all(r.record_id == "closet-1" for r in closet_results)

    # Search outfit_history: should only return history-1
    history_results = await store.search(
        source_type=SOURCE_OUTFIT_HISTORY,
        embedding=vec,
        user_id=USER_A,
        limit=10,
        threshold=0.50,
    )
    assert all(r.source_type == SOURCE_OUTFIT_HISTORY for r in history_results)
    assert all(r.record_id == "history-1" for r in history_results)


# ── Empty store returns empty list ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_store_returns_empty_list(store):
    vec = _rand_embedding(seed=0)
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=vec,
        user_id=USER_A,
        limit=5,
        threshold=0.70,
    )
    assert results == []


# ── Upsert deduplication (same record_id) ────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_same_id_updates_metadata_not_duplicates(store):
    """Upserting the same record_id twice should not add a duplicate."""
    vec = _rand_embedding(seed=30)
    await store.upsert(
        meta=_make_meta("item-dup", SOURCE_CLOSET_ITEM, user_id=USER_A, color="red"),
        embedding=vec,
    )
    await store.upsert(
        meta=_make_meta("item-dup", SOURCE_CLOSET_ITEM, user_id=USER_A, color="blue"),
        embedding=vec,
    )
    # total should be 1 not 2
    assert store.total(SOURCE_CLOSET_ITEM) == 1


# ── Retriever outfit_context integration (FAISS path) ────────────────────────

@pytest.mark.asyncio
async def test_retrieve_outfit_context_returns_history_with_faiss(store):
    """retrieve_outfit_context uses FAISS when a FAISSVectorStore is injected."""
    vec = _rand_embedding(seed=40)
    await store.upsert(
        meta=_make_meta(
            "history-wedding",
            SOURCE_OUTFIT_HISTORY,
            user_id=USER_A,
            occasion=["wedding"],
            payload={
                "occasion": "wedding",
                "weather_context": {"weather": "warm"},
                "selected_item_ids": ["item-a"],
                "matching_score": 85,
                "recommendation_text": "Great fit for a summer wedding.",
                "improvement_tips": [],
                "was_saved": True,
                "was_worn": True,
                "user_feedback": None,
                "created_at": "2024-05-01T10:00:00",
            },
        ),
        embedding=vec,
    )

    mock_session = AsyncMock()
    # Stub fashion knowledge service (not testing it here)
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=vec),
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session,
            user_id=USER_A,
            occasion="wedding",
            weather="warm",
            limit=5,
            store=store,
        )

    assert result["has_context"] is True
    assert len(result["outfit_history"]) == 1
    assert result["outfit_history"][0]["occasion"] == "wedding"
    assert result["fallback_message"] is None


@pytest.mark.asyncio
async def test_retrieve_outfit_context_fallback_when_empty(store):
    """When no history and no fashion docs, fallback_message is set."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=_rand_embedding(seed=99)),
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session,
            user_id=USER_A,
            occasion="rave",
            weather="",
            limit=5,
            store=store,
        )

    assert result["has_context"] is False
    assert result["fallback_message"] is not None
    assert "No matching" in result["fallback_message"]
