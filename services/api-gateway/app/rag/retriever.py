"""
High-level RAG retrieval orchestration for CLOZEHIVE.

Each public function corresponds to one of the five RAG use cases:

    retrieve_outfit_context    — fashion knowledge + user's outfit history
    retrieve_packing_context   — user's previous trip packing memories
    retrieve_similar_items     — visually/semantically similar closet items
    retrieve_purchase_gaps     — detected wardrobe gaps ranked by priority

Design
──────
- All functions accept user_id and enforce it at every retrieval call.
- Embedding generation failures are handled gracefully (empty context returned).
- Similarity thresholds are constants here; not exposed as user-controlled params
  to prevent callers from bypassing quality gates.
- The `vector_store` parameter is optional; when None the application singleton
  is used (production). Tests inject a FAISSVectorStore to avoid DB dependency.
- Every function returns a typed result so the caller never receives None.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.rag.vector_store import (
    FAISSVectorStore,
    PGVectorStore,
    SOURCE_CLOSET_ITEM,
    SOURCE_FASHION_KNOWLEDGE,
    SOURCE_OUTFIT_HISTORY,
    SOURCE_PACKING_MEMORY,
    get_vector_store,
)
from app.services import (
    closet_similarity_service,
    fashion_rag_service,
    outfit_history_service,
    packing_memory_service,
    purchase_gap_service,
)
from app.services.embedding_service import generate_text_embedding

logger = get_logger("rag.retriever")

# ── Similarity thresholds ─────────────────────────────────────────────────────
# These are quality gates; lower = more results but noisier matches.

_THRESHOLD_FASHION = 0.60     # fashion documents are broadly relevant at 0.60
_THRESHOLD_OUTFIT_HISTORY = 0.65
_THRESHOLD_PACKING = 0.60
_THRESHOLD_CLOSET_TEXT = 0.60
_THRESHOLD_CLOSET_ITEM = 0.65

# ── Outfit context ────────────────────────────────────────────────────────────


async def retrieve_outfit_context(
    session: AsyncSession,
    user_id: str,
    occasion: str,
    weather: str = "",
    limit: int = 5,
    store: FAISSVectorStore | PGVectorStore | None = None,
) -> dict[str, Any]:
    """
    Retrieve combined fashion knowledge + user's outfit history for an occasion.

    Combines two retrieval sources:
      1. Fashion knowledge (global) — general styling rules for this occasion/weather.
      2. User's outfit history (user-scoped) — past recommendations the user has
         actually worn or saved, weighted by similarity to the current request.

    Returns a dict matching OutfitContextResponse schema.
    """
    _store = store or get_vector_store()
    query = f"Occasion: {occasion}. Weather: {weather}".strip(". ")

    # 1. Fashion knowledge (global, no user_id filter)
    fashion_docs = await fashion_rag_service.search_fashion_knowledge(
        session, query, limit=3, category=None
    )

    # 2. Outfit history (user-scoped) — use existing service which handles
    #    embedding + pgvector search internally.  When using FAISS backend we
    #    fall through to a direct store search instead.
    if isinstance(_store, PGVectorStore):
        outfit_history = await outfit_history_service.search_similar_outfit_history(
            session,
            user_id=user_id,
            occasion=occasion,
            weather=weather,
            limit=limit,
        )
    else:
        outfit_history = await _faiss_outfit_history_search(
            _store, user_id=user_id, occasion=occasion, weather=weather, limit=limit
        )

    has_context = bool(fashion_docs or outfit_history)

    return {
        "occasion": occasion,
        "weather": weather,
        "fashion_knowledge": fashion_docs,
        "outfit_history": outfit_history,
        "has_context": has_context,
        "fallback_message": (
            None if has_context
            else "No matching fashion context found. Using general styling principles."
        ),
    }


async def _faiss_outfit_history_search(
    store: FAISSVectorStore,
    *,
    user_id: str,
    occasion: str,
    weather: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Outfit history search via FAISS backend (used in tests/local dev)."""
    query = f"Occasion: {occasion}. Weather: {weather}".strip(". ")
    embedding = await generate_text_embedding(query)
    if not embedding:
        return []
    results = await store.search(
        source_type=SOURCE_OUTFIT_HISTORY,
        embedding=embedding,
        user_id=user_id,
        limit=limit,
        threshold=_THRESHOLD_OUTFIT_HISTORY,
    )
    return [
        {
            "id": r.record_id,
            "occasion": r.payload.get("occasion"),
            "weather_context": r.payload.get("weather_context"),
            "selected_item_ids": r.payload.get("selected_item_ids") or [],
            "matching_score": r.payload.get("matching_score"),
            "recommendation_text": r.payload.get("recommendation_text"),
            "improvement_tips": r.payload.get("improvement_tips") or [],
            "was_saved": r.payload.get("was_saved", False),
            "was_worn": r.payload.get("was_worn", False),
            "user_feedback": r.payload.get("user_feedback"),
            "similarity_score": r.similarity_score,
            "created_at": str(r.payload.get("created_at", "")),
        }
        for r in results
    ]


# ── Packing context ───────────────────────────────────────────────────────────


async def retrieve_packing_context(
    session: AsyncSession,
    user_id: str,
    destination: str,
    purpose: str,
    weather_summary: dict[str, Any] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 5,
    store: FAISSVectorStore | PGVectorStore | None = None,
) -> dict[str, Any]:
    """
    Retrieve packing memories from the user's past trips.

    Finds trips with semantically similar destination, purpose, and weather to
    surface items that worked well (or were missing) in comparable trips.

    Returns a dict matching PackingContextResponse schema.
    """
    _store = store or get_vector_store()

    if isinstance(_store, PGVectorStore):
        packing_history = await packing_memory_service.search_similar_packing_memories(
            session,
            user_id=user_id,
            destination=destination,
            purpose=purpose,
            weather_summary=weather_summary,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    else:
        packing_history = await _faiss_packing_search(
            _store,
            user_id=user_id,
            destination=destination,
            purpose=purpose,
            weather_summary=weather_summary,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    has_context = bool(packing_history)

    return {
        "destination": destination,
        "purpose": purpose,
        "packing_history": packing_history,
        "has_context": has_context,
        "fallback_message": (
            None if has_context
            else "No previous packing data for this type of trip. Starting fresh."
        ),
    }


async def _faiss_packing_search(
    store: FAISSVectorStore,
    *,
    user_id: str,
    destination: str,
    purpose: str,
    weather_summary: dict[str, Any] | None,
    start_date: str | None,
    end_date: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Packing memory search via FAISS backend."""
    parts = [f"Destination: {destination}", f"Purpose: {purpose}"]
    if start_date and end_date:
        parts.append(f"Dates: {start_date} to {end_date}")
    if weather_summary:
        cond = weather_summary.get("dominant_condition", "")
        if cond:
            parts.append(f"Weather: {cond}")
    query = ". ".join(parts)

    embedding = await generate_text_embedding(query)
    if not embedding:
        return []
    results = await store.search(
        source_type=SOURCE_PACKING_MEMORY,
        embedding=embedding,
        user_id=user_id,
        limit=limit,
        threshold=_THRESHOLD_PACKING,
    )
    return [
        {
            "id": r.record_id,
            "destination": r.payload.get("destination", destination),
            "purpose": r.payload.get("purpose"),
            "start_date": r.payload.get("start_date"),
            "end_date": r.payload.get("end_date"),
            "weather_summary": r.payload.get("weather_summary"),
            "packed_item_ids": r.payload.get("packed_item_ids") or [],
            "missing_items": r.payload.get("missing_items") or [],
            "user_feedback": r.payload.get("user_feedback"),
            "similarity_score": r.similarity_score,
            "created_at": str(r.payload.get("created_at", "")),
        }
        for r in results
    ]


# ── Similar items ─────────────────────────────────────────────────────────────


async def retrieve_similar_items(
    session: AsyncSession,
    user_id: str,
    closet_item_id: str | None = None,
    query: str | None = None,
    image_url: str | None = None,
    limit: int = 5,
    store: FAISSVectorStore | PGVectorStore | None = None,
) -> dict[str, Any]:
    """
    Find similar items in the user's closet.

    Accepts exactly one input signal:
      - closet_item_id: find items similar to an existing owned item
      - query: find items matching a natural-language description
      - image_url: find visually similar items (MVP: text fallback via URL path)

    User isolation: only items belonging to user_id are returned.
    Returns a dict matching SimilarItemsResponse schema.
    """
    _store = store or get_vector_store()

    results: list[dict[str, Any]] = []
    query_type = "none"
    query_ref: str | None = None

    if isinstance(_store, PGVectorStore):
        # Delegate to the existing closet_similarity_service (pgvector path)
        if closet_item_id:
            results = await closet_similarity_service.find_similar_by_item_id(
                session, closet_item_id, user_id, limit=limit
            )
            query_type, query_ref = "closet_item", closet_item_id
        elif query:
            results = await closet_similarity_service.find_similar_by_text(
                session, query, user_id, limit=limit
            )
            query_type, query_ref = "text_query", query
        elif image_url:
            results = await closet_similarity_service.find_similar_by_image_url(
                session, image_url, user_id, limit=limit
            )
            query_type, query_ref = "image_url", image_url
    else:
        results, query_type, query_ref = await _faiss_similar_items(
            _store,
            session=session,
            user_id=user_id,
            closet_item_id=closet_item_id,
            query=query,
            image_url=image_url,
            limit=limit,
        )

    return {
        "query_type": query_type,
        "query_ref": query_ref,
        "count": len(results),
        "results": results,
        "has_results": bool(results),
    }


async def _faiss_similar_items(
    store: FAISSVectorStore,
    *,
    session: AsyncSession,
    user_id: str,
    closet_item_id: str | None,
    query: str | None,
    image_url: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Similar items search via FAISS backend."""
    from app.services.embedding_service import item_to_embedding_text

    text: str | None = None
    query_type = "none"
    query_ref: str | None = None

    if closet_item_id:
        # Load the closet item from DB to build embedding text
        from app.models.closet import ClosetItem
        import uuid as _uuid
        try:
            item = await session.get(ClosetItem, _uuid.UUID(closet_item_id))
        except Exception:
            item = None
        if item and str(item.user_id) == user_id and not item.is_archived:
            text = item_to_embedding_text({
                "name": item.name, "category": item.category, "color": item.color,
                "fabric": item.fabric, "pattern": item.pattern, "season": item.season,
                "occasion": item.occasion, "tags": item.tags,
            })
            query_type, query_ref = "closet_item", closet_item_id
    elif query:
        text = query
        query_type, query_ref = "text_query", query
    elif image_url:
        text = f"Image: {image_url.split('/')[-1]}"
        query_type, query_ref = "image_url", image_url

    if not text:
        return [], query_type, query_ref

    embedding = await generate_text_embedding(text)
    if not embedding:
        return [], query_type, query_ref

    threshold = _THRESHOLD_CLOSET_ITEM if closet_item_id else _THRESHOLD_CLOSET_TEXT
    hits = await store.search(
        source_type=SOURCE_CLOSET_ITEM,
        embedding=embedding,
        user_id=user_id,
        limit=limit,
        threshold=threshold,
        extra_where=f"AND id != '{closet_item_id}'::uuid" if closet_item_id else "",
    )

    results = [
        {
            "item_id": r.record_id,
            "name": r.payload.get("name", ""),
            "category": r.category or "",
            "color": r.color or "",
            "brand": r.payload.get("brand") or "",
            "image_url": r.payload.get("image_url") or r.payload.get("processed_image_url") or "",
            "similarity_score": r.similarity_score,
            "reason": _similarity_reason(r.similarity_score, r.category or "item", r.color),
        }
        for r in hits
    ]
    return results, query_type, query_ref


def _similarity_reason(score: float, category: str, color: str | None) -> str:
    if score >= 0.90:
        return f"Very similar {category}" + (f" — {color}" if color else "")
    if score >= 0.80:
        return f"Similar {category} — matching style and occasion"
    return f"Related {category} — shares some attributes"


# ── Purchase gaps ─────────────────────────────────────────────────────────────


async def retrieve_purchase_gaps(
    session: AsyncSession,
    user_id: str,
    resolved: bool = False,
    limit: int = 30,
) -> dict[str, Any]:
    """
    Retrieve the user's wardrobe gaps ranked by priority score.

    Purchase gap detection is analysis-based (no embedding needed): gaps are
    detected when outfits are generated and packing plans are saved.
    This function retrieves pre-computed gaps from the purchase_gaps table.

    Returns a dict matching PurchaseGapsResponse schema.
    """
    gaps = await purchase_gap_service.get_purchase_gaps(
        session, user_id, resolved=resolved, limit=limit
    )

    if gaps:
        top_cats = [g["missing_category"] for g in gaps[:3]]
        summary = f"Top wardrobe gaps: {', '.join(top_cats)}."
    else:
        summary = "No open wardrobe gaps detected."

    return {
        "count": len(gaps),
        "gaps": gaps,
        "has_gaps": bool(gaps),
        "summary": summary,
    }
