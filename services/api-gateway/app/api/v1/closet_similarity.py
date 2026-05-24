"""Closet similarity search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.services import closet_similarity_service

router = APIRouter(prefix="/closet", tags=["Closet Similarity"])


# ── Request / Response models ─────────────────────────────────────────────────

class CheckSimilarRequest(BaseModel):
    """
    Metadata of a NEW (not-yet-saved) item to check against the user's closet.
    All fields are optional; the more provided, the better the match quality.
    """
    name: str | None = None
    category: str = ""
    subcategory: str | None = None
    color: str | None = None
    colors: list[str] = Field(default_factory=list)
    pattern: str | None = None
    material: str | None = None
    style_tags: list[str] = Field(default_factory=list)
    occasion_tags: list[str] = Field(default_factory=list)
    season_tags: list[str] = Field(default_factory=list)
    limit: int = Field(5, ge=1, le=10)


class SimilarItemOut(BaseModel):
    id: str
    item_id: str
    name: str
    category: str
    color: str
    colors: list[str]
    brand: str
    image_url: str
    similarity_score: int              # 0–100
    similarity_label: str              # "Possible duplicate" | "Very similar" | "Related item"
    similarity_reason: str             # Why they are similar
    difference_summary: str            # Key differences


class CheckSimilarResponse(BaseModel):
    similar_items: list[SimilarItemOut]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/check-similar", response_model=CheckSimilarResponse)
async def check_similar_before_save(
    body: CheckSimilarRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """
    Check if a newly analyzed clothing item is similar to items already in the user's closet.

    Call this BEFORE confirming/saving a new item so the user can decide whether to skip
    saving (possible duplicate), adjust details, or save anyway.

    Uses embedding-based cosine similarity with a metadata-score fallback.
    Never raises — returns empty list on any error to never block the save flow.
    """
    try:
        # Normalise: prefer first element of colors[] over color field
        effective_color = body.color or (body.colors[0] if body.colors else None)

        metadata = {
            "name": body.name or "",
            "category": body.category,
            "subcategory": body.subcategory,
            "color": effective_color,
            "colors": body.colors,
            "pattern": body.pattern,
            "material": body.material,
            "style_tags": body.style_tags,
            "occasion_tags": body.occasion_tags,
            "season_tags": body.season_tags,
        }

        results = await closet_similarity_service.check_similar_for_new_item(
            session,
            user_id,
            source_metadata=metadata,
            limit=body.limit,
            threshold_score=55,
        )
        return {"similar_items": results}
    except Exception as exc:
        # Safety: never block user from saving if similarity check fails
        import logging
        logging.getLogger("closet_similarity").warning(
            "check_similar_failed: %s", exc, exc_info=True
        )
        return {"similar_items": []}


@router.get("/items/{item_id}/similar", response_model=CheckSimilarResponse)
async def get_similar_items_for_closet_item(
    item_id: str,
    user_id: CurrentUser,
    session: DbSession,
    limit: int = Query(6, ge=1, le=20),
):
    """
    GET similar items for an existing closet item (shown inside item detail view).
    Returns items scored ≥55 with similarity_label and difference_summary.
    """
    try:
        results = await closet_similarity_service.find_similar_by_item_id(
            session, item_id, user_id, limit=limit
        )
        return {"similar_items": results}
    except Exception:
        return {"similar_items": []}


# ── Legacy endpoints (kept for backward compat) ───────────────────────────────

@router.post("/similar")
async def find_similar_closet_items(
    user_id: CurrentUser,
    session: DbSession,
    closet_item_id: str | None = Query(None),
    query: str | None = Query(None),
    image_url: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
):
    """Legacy endpoint — find similar items by item ID, text, or image URL."""
    if closet_item_id:
        results = await closet_similarity_service.find_similar_by_item_id(
            session, closet_item_id, user_id, limit=limit
        )
        return {"query_type": "closet_item", "query_ref": closet_item_id,
                "count": len(results), "results": results}
    if query:
        results = await closet_similarity_service.find_similar_by_text(
            session, query, user_id, limit=limit
        )
        return {"query_type": "text_query", "query_ref": query,
                "count": len(results), "results": results}
    if image_url:
        results = await closet_similarity_service.find_similar_by_image_url(
            session, image_url, user_id, limit=limit
        )
        return {"query_type": "image_url", "query_ref": image_url,
                "count": len(results), "results": results}
    return {"query_type": "none", "message": "Provide one of: closet_item_id, query, or image_url",
            "results": []}


@router.get("/similar/{item_id}")
async def get_similar_to_item(
    item_id: str,
    user_id: CurrentUser,
    session: DbSession,
    limit: int = Query(5, ge=1, le=20),
):
    """Legacy GET endpoint — find items similar to a closet item."""
    results = await closet_similarity_service.find_similar_by_item_id(
        session, item_id, user_id, limit=limit
    )
    return {"query_type": "closet_item", "item_id": item_id,
            "count": len(results), "results": results}
