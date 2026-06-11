"""Shopping Check endpoints — in-store buy/skip advisor + closet match."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status
from pydantic import BaseModel

from app.api.v1.intelligence.services import shopping_check_service
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.core.upload_service import delete_upload, persist_upload, read_validated_image

router = APIRouter(prefix="/shopping", tags=["Shopping Check"])


@router.post("/check", status_code=status.HTTP_201_CREATED)
async def check_shopping_item(
    user_id: CurrentUser,
    session: DbSession,
    file: UploadFile = File(..., description="Photo of the item you want to buy"),
):
    """
    Upload a photo of an in-store item and get an AI-powered buy recommendation.

    Returns:
    - Item analysis (category, color, material, etc.)
    - Matched items from your closet
    - Buy score 0-100
    - Recommendation: buy / consider / skip
    - Closet boost % — how much this improves your wardrobe completeness
    - Plain-English reasoning
    """
    image_bytes, media_type = await read_validated_image(file)

    # Persist image (best-effort — analysis still runs if storage fails)
    image_url: str | None = None
    try:
        image_url = await persist_upload(image_bytes, media_type)
    except Exception:
        pass

    result = await shopping_check_service.analyze_shopping_item(
        image_bytes=image_bytes,
        media_type=media_type,
        user_id=user_id,
        session=session,
        image_url=image_url,
    )
    return result


class PurchaseDecisionRequest(BaseModel):
    bought: bool


@router.patch("/{check_id}/decision", status_code=status.HTTP_200_OK)
async def record_purchase_decision(
    check_id: UUID,
    body: PurchaseDecisionRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """Record whether the user actually purchased the checked item."""
    result = await shopping_check_service.record_purchase_decision(
        check_id=str(check_id),
        user_id=user_id,
        bought=body.bought,
        session=session,
    )
    if not result:
        raise NotFoundError("Shopping check not found")
    return result


@router.get("/history", status_code=status.HTTP_200_OK)
async def get_shopping_history(
    user_id: CurrentUser,
    session: DbSession,
    limit: int = Query(30, ge=1, le=100),
):
    """Return the user's recent shopping checks, newest first."""
    checks = await shopping_check_service.get_shopping_history(
        user_id=user_id,
        session=session,
        limit=limit,
    )
    return {"count": len(checks), "checks": checks}


@router.delete("/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_check(
    check_id: UUID,
    user_id: CurrentUser,
    session: DbSession,
    background_tasks: BackgroundTasks,
):
    """Delete a shopping check from the user's history."""
    found, image_url = await shopping_check_service.delete_shopping_check(
        check_id=str(check_id),
        user_id=user_id,
        session=session,
    )
    if not found:
        raise NotFoundError("Shopping check not found")
    if image_url:
        background_tasks.add_task(delete_upload, image_url)


# ── Closet → Shopping ─────────────────────────────────────────────────────────


class ClosetMatchRequest(BaseModel):
    closet_item_id: str


@router.post("/closet-match", status_code=status.HTTP_200_OK)
async def get_closet_match_suggestions(
    body: ClosetMatchRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """
    Given a closet item, return AI shopping suggestions for what to buy next
    to maximise outfit versatility (the "Complete My Look" flow).
    """
    result = await shopping_check_service.get_closet_match_suggestions(
        closet_item_id=body.closet_item_id,
        user_id=user_id,
        session=session,
    )
    if not result:
        raise NotFoundError("Closet item not found")
    return result


@router.post("/{check_id}/add-to-closet", status_code=status.HTTP_201_CREATED)
async def add_shopping_item_to_closet(
    check_id: UUID,
    user_id: CurrentUser,
    session: DbSession,
):
    """
    Create a closet item directly from an analysed shopping check — no
    re-upload needed. Use this when the user decides to buy the item.
    """
    item = await shopping_check_service.add_shopping_item_to_closet(
        check_id=str(check_id),
        user_id=user_id,
        session=session,
    )
    if not item:
        raise NotFoundError("Shopping check not found")
    return {"closet_item": item}
