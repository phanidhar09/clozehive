"""
Unified RAG endpoints — /api/v1/rag/*

Four retrieval endpoints, each backed by one of the five RAG use cases:

    GET  /api/v1/rag/outfit-context    — fashion knowledge + outfit history
    GET  /api/v1/rag/packing-context   — previous trip packing memories
    POST /api/v1/rag/similar-items     — visually/semantically similar closet items
    GET  /api/v1/rag/purchase-gaps     — detected wardrobe gaps

All endpoints:
  - Require a valid JWT (CurrentUser dependency)
  - Are strictly user-scoped: retrieval is filtered by the authenticated user's id
  - Return structured fallback responses when no relevant context is found
  - Apply similarity thresholds internally — callers never see junk matches
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.rag import retriever
from app.rag.schemas import (
    OutfitContextResponse,
    PackingContextResponse,
    PurchaseGapsResponse,
    SimilarItemsRequest,
    SimilarItemsResponse,
)

router = APIRouter(prefix="/rag", tags=["RAG"])


# ── GET /api/v1/rag/outfit-context ────────────────────────────────────────────


@router.get(
    "/outfit-context",
    response_model=OutfitContextResponse,
    summary="Retrieve fashion knowledge + past outfit history for an occasion",
)
async def get_outfit_context(
    user_id: CurrentUser,
    session: DbSession,
    occasion: str = Query(..., min_length=1, max_length=100, description="Target occasion, e.g. 'wedding', 'business casual'"),
    weather: str = Query("", max_length=100, description="Optional weather description, e.g. 'warm and sunny'"),
    limit: int = Query(5, ge=1, le=10, description="Max outfit history records to return"),
):
    """
    Retrieves two sources of context for AI outfit generation:

    1. **Fashion knowledge** — general rules for the requested occasion and weather
       (color matching, dress codes, layering, fabric guidance).
    2. **Outfit history** — the user's past outfit recommendations for similar
       occasions, ranked by semantic similarity.  Includes wear/save feedback.

    **Fallback**: if no relevant context is found, `has_context` is false and
    `fallback_message` provides a safe default message for the AI prompt.
    """
    result = await retriever.retrieve_outfit_context(
        session,
        user_id=user_id,
        occasion=occasion,
        weather=weather,
        limit=limit,
    )
    return OutfitContextResponse(**result)


# ── GET /api/v1/rag/packing-context ─────────────────────────────────────────


@router.get(
    "/packing-context",
    response_model=PackingContextResponse,
    summary="Retrieve past packing memories for a trip",
)
async def get_packing_context(
    user_id: CurrentUser,
    session: DbSession,
    destination: str = Query(..., min_length=1, max_length=255, description="Trip destination"),
    purpose: str = Query(..., min_length=1, max_length=50, description="Trip purpose, e.g. 'leisure', 'business'"),
    start_date: str | None = Query(None, description="Trip start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="Trip end date (YYYY-MM-DD)"),
    limit: int = Query(5, ge=1, le=10, description="Max packing memory records to return"),
):
    """
    Retrieves the user's past packing experiences from semantically similar trips.

    Similarity is computed over destination + purpose + dates + weather, so
    'Paris, leisure, spring' matches past trips to similar European city-break trips.

    **Gap integration**: missing_items from past trips surface items the user should
    consider purchasing (see /rag/purchase-gaps).

    **Fallback**: `has_context` is false when no matching previous trips are found.
    """
    result = await retriever.retrieve_packing_context(
        session,
        user_id=user_id,
        destination=destination,
        purpose=purpose,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return PackingContextResponse(**result)


# ── POST /api/v1/rag/similar-items ───────────────────────────────────────────


@router.post(
    "/similar-items",
    response_model=SimilarItemsResponse,
    summary="Find visually or semantically similar items in the user's closet",
)
async def find_similar_items(
    user_id: CurrentUser,
    session: DbSession,
    body: SimilarItemsRequest,
):
    """
    Finds items in the user's closet that are similar to a given reference.

    Accepts exactly one of:
    - **closet_item_id** — find items similar to an existing owned item (by embedding)
    - **query** — find items matching a natural-language description
      (e.g. "light blue casual shirt for summer")
    - **image_url** — find visually similar items
      (MVP: text fallback via URL metadata; CLIP-based visual embeddings planned)

    **User isolation**: only returns items belonging to the authenticated user.
    Items below the similarity threshold are silently excluded.
    """
    result = await retriever.retrieve_similar_items(
        session,
        user_id=user_id,
        closet_item_id=body.closet_item_id,
        query=body.query,
        image_url=body.image_url,
        limit=body.limit,
    )
    return SimilarItemsResponse(**result)


# ── GET /api/v1/rag/purchase-gaps ────────────────────────────────────────────


@router.get(
    "/purchase-gaps",
    response_model=PurchaseGapsResponse,
    summary="Retrieve detected wardrobe gaps ranked by priority",
)
async def get_purchase_gaps(
    user_id: CurrentUser,
    session: DbSession,
    resolved: bool = Query(False, description="Include already-resolved gaps"),
    limit: int = Query(30, ge=1, le=100, description="Max gaps to return"),
):
    """
    Returns the user's wardrobe gaps in priority order.

    Gaps are auto-detected from three sources:
    - **Structural gaps** — essential categories missing entirely (no shoes, no tops, etc.)
    - **Trip gaps** — items flagged as 'you might still need' in past packing plans
    - **Outfit gaps** — pieces missing to complete a specific outfit look

    Gaps are **not** product recommendations — they identify *categories* the user
    should consider acquiring based on their own closet and usage patterns.

    Use `PATCH /api/v1/purchase-gaps/{gap_id}/resolve` to mark a gap resolved.
    """
    result = await retriever.retrieve_purchase_gaps(
        session,
        user_id=user_id,
        resolved=resolved,
        limit=limit,
    )
    return PurchaseGapsResponse(**result)
