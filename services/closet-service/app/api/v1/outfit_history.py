"""Outfit History RAG endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.services import outfit_history_service

router = APIRouter(prefix="/outfits/history", tags=["Outfit History"])


class OutfitFeedbackRequest(BaseModel):
    feedback: str | None = None
    was_worn: bool | None = None
    was_saved: bool | None = None


@router.get("/")
async def list_outfit_history(
    user_id: CurrentUser,
    session: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List the user's outfit history, newest first."""
    records = await outfit_history_service.list_outfit_history(
        session, user_id, limit=limit, offset=offset
    )
    return {"count": len(records), "results": records}


@router.get("/similar")
async def get_similar_outfit_history(
    user_id: CurrentUser,
    session: DbSession,
    occasion: str = Query(..., min_length=1, max_length=100),
    weather: str = Query("", max_length=100),
    limit: int = Query(5, ge=1, le=10),
):
    """
    Retrieve past outfit recommendations similar to the requested occasion and weather.

    Use this to surface "Based on your previous outfits" suggestions in the UI.
    """
    results = await outfit_history_service.search_similar_outfit_history(
        session, user_id, occasion=occasion, weather=weather, limit=limit
    )
    return {
        "occasion": occasion,
        "weather": weather,
        "count": len(results),
        "results": results,
    }


@router.post("/{history_id}/feedback", status_code=status.HTTP_200_OK)
async def submit_outfit_feedback(
    history_id: str,
    body: OutfitFeedbackRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """Submit feedback on a past outfit recommendation."""
    result = await outfit_history_service.update_outfit_feedback(
        session,
        history_id=history_id,
        user_id=user_id,
        feedback=body.feedback,
        was_worn=body.was_worn,
        was_saved=body.was_saved,
    )
    if not result:
        raise NotFoundError("Outfit history record not found")
    return result
