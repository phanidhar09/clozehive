"""
Unit tests — RAG user isolation.

These tests prove that no user can ever retrieve another user's data.

Every RAG store and retriever call is tested:
  1. FAISS vector store — user_id filter applied after candidate retrieval.
  2. pgvector store — WHERE user_id clause enforced at SQL level (tested via
     the existing pgvector_cosine_search mock).
  3. Retriever functions — never pass a different user_id to a search call.

Tests use two distinct users (USER_A, USER_B) and assert that USER_A's query
never surfaces USER_B's items and vice versa.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, call, patch

import pytest

from app.rag.vector_store import (
    EmbeddingMeta,
    FAISSVectorStore,
    PGVectorStore,
    SOURCE_CLOSET_ITEM,
    SOURCE_OUTFIT_HISTORY,
    SOURCE_PACKING_MEMORY,
)
from app.rag import retriever


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unit_vector(seed: int) -> list[float]:
    import numpy as np
    rng = np.random.default_rng(seed)
    v = rng.random(1536).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())


@pytest.fixture
def store() -> FAISSVectorStore:
    return FAISSVectorStore(index_dir=None)


# ── FAISS: user A cannot see user B's items ───────────────────────────────────

@pytest.mark.asyncio
async def test_faiss_user_a_cannot_see_user_b_items(store):
    """USER_A's query must never return USER_B's vectors."""
    shared_vec = _unit_vector(1)   # identical vector — worst case for leakage

    # Insert USER_B's item
    await store.upsert(
        meta=EmbeddingMeta(
            record_id="b-item-1",
            source_type=SOURCE_CLOSET_ITEM,
            user_id=USER_B,
            category="tops",
        ),
        embedding=shared_vec,
    )

    # USER_A searches with the exact same vector
    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=shared_vec,
        user_id=USER_A,
        limit=10,
        threshold=0.50,
    )
    assert results == [], "USER_A must not see USER_B's items"


@pytest.mark.asyncio
async def test_faiss_user_b_cannot_see_user_a_items(store):
    """Mirror test: USER_B query must not return USER_A's vectors."""
    shared_vec = _unit_vector(2)

    await store.upsert(
        meta=EmbeddingMeta(
            record_id="a-item-1",
            source_type=SOURCE_CLOSET_ITEM,
            user_id=USER_A,
            category="bottoms",
        ),
        embedding=shared_vec,
    )

    results = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=shared_vec,
        user_id=USER_B,
        limit=10,
        threshold=0.50,
    )
    assert results == [], "USER_B must not see USER_A's items"


@pytest.mark.asyncio
async def test_faiss_user_sees_only_own_items_in_mixed_store(store):
    """USER_A items plus USER_B items in the same index; each user sees only their own."""
    vec_a = _unit_vector(3)
    vec_b = _unit_vector(4)
    shared = _unit_vector(5)

    await store.upsert(
        meta=EmbeddingMeta("a1", SOURCE_CLOSET_ITEM, user_id=USER_A),
        embedding=vec_a,
    )
    await store.upsert(
        meta=EmbeddingMeta("a2", SOURCE_CLOSET_ITEM, user_id=USER_A),
        embedding=shared,
    )
    await store.upsert(
        meta=EmbeddingMeta("b1", SOURCE_CLOSET_ITEM, user_id=USER_B),
        embedding=vec_b,
    )
    await store.upsert(
        meta=EmbeddingMeta("b2", SOURCE_CLOSET_ITEM, user_id=USER_B),
        embedding=shared,
    )

    results_a = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=shared,
        user_id=USER_A,
        limit=10,
        threshold=0.50,
    )
    ids_a = {r.record_id for r in results_a}
    assert "a2" in ids_a, "USER_A must see their own item"
    assert "b1" not in ids_a, "USER_A must not see USER_B's item (different vector)"
    assert "b2" not in ids_a, "USER_A must not see USER_B's item (same vector)"

    results_b = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=shared,
        user_id=USER_B,
        limit=10,
        threshold=0.50,
    )
    ids_b = {r.record_id for r in results_b}
    assert "b2" in ids_b, "USER_B must see their own item"
    assert "a1" not in ids_b, "USER_B must not see USER_A's item"
    assert "a2" not in ids_b, "USER_B must not see USER_A's item (same vector)"


# ── FAISS: global knowledge accessible to all users ──────────────────────────

@pytest.mark.asyncio
async def test_global_knowledge_visible_to_all_users(store):
    """Fashion knowledge docs have user_id=None and must be visible to every user."""
    vec = _unit_vector(10)
    await store.upsert(
        meta=EmbeddingMeta(
            "fashion-doc-1",
            SOURCE_CLOSET_ITEM,
            user_id=None,   # global
            category="color",
        ),
        embedding=vec,
    )

    for querying_user in (USER_A, USER_B, str(uuid.uuid4())):
        results = await store.search(
            source_type=SOURCE_CLOSET_ITEM,
            embedding=vec,
            user_id=querying_user,
            limit=5,
            threshold=0.50,
        )
        assert any(r.record_id == "fashion-doc-1" for r in results), (
            f"Global doc must be visible to user {querying_user}"
        )


# ── FAISS: outcome_history user isolation ─────────────────────────────────────

@pytest.mark.asyncio
async def test_faiss_outfit_history_user_isolation(store):
    """Outfit history entries from USER_B must never appear in USER_A's results."""
    vec = _unit_vector(20)

    await store.upsert(
        meta=EmbeddingMeta(
            "oh-b-1",
            SOURCE_OUTFIT_HISTORY,
            user_id=USER_B,
            payload={"occasion": "formal", "selected_item_ids": []},
        ),
        embedding=vec,
    )

    results = await store.search(
        source_type=SOURCE_OUTFIT_HISTORY,
        embedding=vec,
        user_id=USER_A,
        limit=5,
        threshold=0.50,
    )
    assert results == []


# ── pgvector: user_id is forwarded to SQL query ───────────────────────────────

@pytest.mark.asyncio
async def test_pgvector_store_forwards_user_id_to_sql():
    """PGVectorStore must always pass user_id to pgvector_cosine_search."""
    pg_store = PGVectorStore()
    mock_session = AsyncMock()

    with patch(
        "app.rag.vector_store.pgvector_cosine_search",
        new=AsyncMock(return_value=[]),
    ) as mock_search:
        await pg_store.search(
            source_type=SOURCE_CLOSET_ITEM,
            embedding=_unit_vector(1),
            user_id=USER_A,
            limit=5,
            threshold=0.70,
            session=mock_session,
        )
    # Verify user_id was forwarded
    _, kwargs = mock_search.call_args
    assert kwargs.get("user_id") == USER_A or mock_search.call_args.args[3] == USER_A


@pytest.mark.asyncio
async def test_pgvector_store_no_session_raises():
    """PGVectorStore.search without a session must raise ValueError (not silently skip)."""
    pg_store = PGVectorStore()
    with pytest.raises(ValueError, match="session"):
        await pg_store.search(
            source_type=SOURCE_CLOSET_ITEM,
            embedding=_unit_vector(1),
            user_id=USER_A,
            session=None,
        )


# ── Retriever: retrieve_outfit_context user isolation ────────────────────────

@pytest.mark.asyncio
async def test_retrieve_outfit_context_passes_correct_user_id(store):
    """retrieve_outfit_context must search outfit history only for the requesting user."""
    vec = _unit_vector(50)

    # Plant USER_B's history
    await store.upsert(
        meta=EmbeddingMeta(
            "oh-b",
            SOURCE_OUTFIT_HISTORY,
            user_id=USER_B,
            payload={
                "occasion": "business casual",
                "weather_context": None,
                "selected_item_ids": [],
                "matching_score": None,
                "recommendation_text": None,
                "improvement_tips": [],
                "was_saved": False,
                "was_worn": False,
                "user_feedback": None,
                "created_at": "",
            },
        ),
        embedding=vec,
    )

    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.fashion_rag_service.search_fashion_knowledge",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=vec),
    ):
        result = await retriever.retrieve_outfit_context(
            mock_session,
            user_id=USER_A,        # <── requesting as USER_A
            occasion="business casual",
            weather="",
            limit=5,
            store=store,
        )

    # USER_A should get no outfit history because only USER_B's record exists
    assert result["outfit_history"] == []


# ── Retriever: retrieve_packing_context user isolation ───────────────────────

@pytest.mark.asyncio
async def test_retrieve_packing_context_isolates_users(store):
    """USER_A must not receive USER_B's packing memory."""
    vec = _unit_vector(60)

    await store.upsert(
        meta=EmbeddingMeta(
            "pm-b",
            SOURCE_PACKING_MEMORY,
            user_id=USER_B,
            payload={
                "destination": "Tokyo",
                "purpose": "leisure",
                "packed_item_ids": ["x"],
                "missing_items": [],
                "user_feedback": None,
                "created_at": "",
            },
        ),
        embedding=vec,
    )

    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=vec),
    ):
        result = await retriever.retrieve_packing_context(
            mock_session,
            user_id=USER_A,
            destination="Tokyo",
            purpose="leisure",
            store=store,
        )

    assert result["packing_history"] == []
    assert result["has_context"] is False


# ── Retriever: retrieve_similar_items user isolation ─────────────────────────

@pytest.mark.asyncio
async def test_retrieve_similar_items_isolates_users(store):
    """USER_A must not receive USER_B's closet items in similarity search."""
    vec = _unit_vector(70)

    await store.upsert(
        meta=EmbeddingMeta(
            "b-shirt",
            SOURCE_CLOSET_ITEM,
            user_id=USER_B,
            category="tops",
            payload={
                "name": "USER_B Shirt",
                "brand": "",
                "image_url": "",
                "processed_image_url": "",
            },
        ),
        embedding=vec,
    )

    mock_session = AsyncMock()
    with patch(
        "app.rag.retriever.generate_text_embedding",
        new=AsyncMock(return_value=vec),
    ):
        result = await retriever.retrieve_similar_items(
            mock_session,
            user_id=USER_A,
            query="casual shirt",
            store=store,
        )

    assert result["results"] == []
    assert result["has_results"] is False
