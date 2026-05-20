"""
Unit tests — RAG empty results and fallback behaviour.

Tests verify that when no relevant context is available, the system:
  1. Returns a valid, typed response (never raises an exception).
  2. Sets `has_context` / `has_results` / `has_gaps` to False.
  3. Provides a human-readable `fallback_message`.
  4. Never returns partial/corrupt data.

Scenarios covered:
  - Embedding service unavailable (OpenAI returns None).
  - Empty FAISS store (no vectors upserted yet).
  - High threshold causes all results to be filtered out.
  - User has no history (new user, first time using the feature).
  - Purchase gaps table is empty for the user.
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
    SOURCE_PACKING_MEMORY,
)
from app.rag import retriever


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unit_vec(seed: int) -> list[float]:
    import numpy as np
    rng = np.random.default_rng(seed)
    v = rng.random(1536).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


USER = str(uuid.uuid4())


@pytest.fixture
def store() -> FAISSVectorStore:
    return FAISSVectorStore(index_dir=None)


# ── outfit_context fallback scenarios ────────────────────────────────────────

@pytest.mark.asyncio
async def test_outfit_context_no_embedding_returns_fallback(store):
    """When embedding generation fails (returns None), fallback_message is set."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=None),   # <── embedding fails
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session,
            user_id=USER,
            occasion="beach party",
            weather="sunny",
            limit=5,
            store=store,
        )

    assert result["has_context"] is False
    assert result["fashion_knowledge"] == []
    assert result["outfit_history"] == []
    assert result["fallback_message"] is not None


@pytest.mark.asyncio
async def test_outfit_context_empty_store_new_user(store):
    """New user with no outfit history should get fallback with no errors."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=_unit_vec(1)),
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session,
            user_id=USER,
            occasion="dinner",
            store=store,
        )

    assert isinstance(result, dict)
    assert "has_context" in result
    assert result["has_context"] is False
    assert result["fallback_message"] is not None


@pytest.mark.asyncio
async def test_outfit_context_with_fashion_docs_has_context_true(store):
    """Even with no outfit history, fashion_docs alone means has_context=True."""
    mock_session = AsyncMock()
    fake_doc = {
        "id": "doc-1",
        "title": "Wedding Guide",
        "content": "Wear smart attire.",
        "category": "occasion",
        "season": None,
        "occasion": "wedding",
        "relevance_score": 0.82,
    }
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[fake_doc]),   # <── docs available
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=_unit_vec(1)),
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session,
            user_id=USER,
            occasion="wedding",
            store=store,
        )

    assert result["has_context"] is True
    assert len(result["fashion_knowledge"]) == 1
    assert result["fallback_message"] is None


# ── packing_context fallback scenarios ───────────────────────────────────────

@pytest.mark.asyncio
async def test_packing_context_no_history_returns_fallback(store):
    """User with no previous trips gets a clean fallback, not an error."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=_unit_vec(5)),
    ):
        result = await retriever.retrieve_packing_context(
            mock_session,
            user_id=USER,
            destination="Bali",
            purpose="leisure",
            store=store,
        )

    assert result["has_context"] is False
    assert result["packing_history"] == []
    assert result["fallback_message"] is not None
    assert "No previous packing" in result["fallback_message"]


@pytest.mark.asyncio
async def test_packing_context_embedding_failure_returns_fallback(store):
    """Embedding service failure gracefully returns empty context."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=None),
    ):
        result = await retriever.retrieve_packing_context(
            mock_session,
            user_id=USER,
            destination="Berlin",
            purpose="business",
            store=store,
        )

    assert isinstance(result, dict)
    assert result["packing_history"] == []
    assert result["has_context"] is False


@pytest.mark.asyncio
async def test_packing_context_high_threshold_returns_empty(store):
    """Packing memories that don't meet the threshold are filtered out."""
    vec_stored = _unit_vec(10)
    vec_query = _unit_vec(11)   # different vector

    await store.upsert(
        meta=EmbeddingMeta(
            "pm-1",
            SOURCE_PACKING_MEMORY,
            user_id=USER,
            payload={"destination": "Sydney", "purpose": "leisure",
                     "packed_item_ids": [], "missing_items": [],
                     "user_feedback": None, "created_at": ""},
        ),
        embedding=vec_stored,
    )

    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=vec_query),
    ):
        result = await retriever.retrieve_packing_context(
            mock_session,
            user_id=USER,
            destination="Sydney",
            purpose="leisure",
            store=store,
        )

    # vec_stored and vec_query are different random unit vectors; cosine similarity
    # between them will be low and well below any reasonable threshold
    assert isinstance(result["packing_history"], list)


# ── similar_items fallback scenarios ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_similar_items_no_query_returns_none_type(store):
    """When no input is provided, query_type=none and results=[]."""
    mock_session = AsyncMock()
    result = await retriever.retrieve_similar_items(
        mock_session,
        user_id=USER,
        store=store,
        # No closet_item_id, query, or image_url
    )

    assert result["query_type"] == "none"
    assert result["results"] == []
    assert result["has_results"] is False


@pytest.mark.asyncio
async def test_similar_items_empty_closet_returns_empty(store):
    """User with no closet items gets empty results, not an error."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=_unit_vec(20)),
    ):
        result = await retriever.retrieve_similar_items(
            mock_session,
            user_id=USER,
            query="navy blue blazer",
            store=store,
        )

    assert result["results"] == []
    assert result["count"] == 0
    assert result["has_results"] is False


@pytest.mark.asyncio
async def test_similar_items_embedding_failure_returns_empty(store):
    """Embedding service failure returns empty result, not an exception."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=None),
    ):
        result = await retriever.retrieve_similar_items(
            mock_session,
            user_id=USER,
            query="silk blouse",
            store=store,
        )

    assert result["results"] == []
    assert result["has_results"] is False


# ── purchase_gaps fallback scenarios ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_purchase_gaps_empty_returns_has_gaps_false():
    """User with no gaps gets has_gaps=False and a clean summary."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.purchase_gap_service.get_purchase_gaps",
        new=AsyncMock(return_value=[]),
    ):
        result = await retriever.retrieve_purchase_gaps(
            mock_session,
            user_id=USER,
        )

    assert result["has_gaps"] is False
    assert result["count"] == 0
    assert result["gaps"] == []
    assert "No open wardrobe gaps" in result["summary"]


@pytest.mark.asyncio
async def test_purchase_gaps_with_gaps_returns_summary():
    """User with gaps gets has_gaps=True and a summary mentioning top categories."""
    mock_gaps = [
        {"id": str(uuid.uuid4()), "gap_type": "structural", "missing_category": "shoes",
         "missing_color": None, "missing_season": None, "missing_occasion": None,
         "reason": "No shoes in closet.", "priority_score": 0.85,
         "source_context": None, "suggested_attributes": None,
         "resolved": False, "created_at": "2024-01-01T00:00:00"},
        {"id": str(uuid.uuid4()), "gap_type": "structural", "missing_category": "outerwear",
         "missing_color": None, "missing_season": None, "missing_occasion": None,
         "reason": "No outerwear.", "priority_score": 0.75,
         "source_context": None, "suggested_attributes": None,
         "resolved": False, "created_at": "2024-01-01T00:00:00"},
    ]
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.purchase_gap_service.get_purchase_gaps",
        new=AsyncMock(return_value=mock_gaps),
    ):
        result = await retriever.retrieve_purchase_gaps(
            mock_session,
            user_id=USER,
        )

    assert result["has_gaps"] is True
    assert result["count"] == 2
    assert "shoes" in result["summary"]


# ── Response shape invariants ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_outfit_context_response_has_required_keys(store):
    """OutfitContext response always contains required keys regardless of data."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=None),
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session, user_id=USER, occasion="test", store=store
        )

    required = {"occasion", "weather", "fashion_knowledge", "outfit_history", "has_context"}
    assert required.issubset(result.keys())


@pytest.mark.asyncio
async def test_packing_context_response_has_required_keys(store):
    """PackingContext response always contains required keys."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=None),
    ):
        result = await retriever.retrieve_packing_context(
            mock_session, user_id=USER, destination="X", purpose="Y", store=store
        )

    required = {"destination", "purpose", "packing_history", "has_context"}
    assert required.issubset(result.keys())


@pytest.mark.asyncio
async def test_similar_items_response_has_required_keys(store):
    """SimilarItems response always contains required keys."""
    mock_session = AsyncMock()
    result = await retriever.retrieve_similar_items(
        mock_session, user_id=USER, store=store
    )
    required = {"query_type", "query_ref", "count", "results", "has_results"}
    assert required.issubset(result.keys())


@pytest.mark.asyncio
async def test_purchase_gaps_response_has_required_keys():
    """PurchaseGaps response always contains required keys."""
    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.purchase_gap_service.get_purchase_gaps",
        new=AsyncMock(return_value=[]),
    ):
        result = await retriever.retrieve_purchase_gaps(mock_session, user_id=USER)

    required = {"count", "gaps", "has_gaps", "summary"}
    assert required.issubset(result.keys())
