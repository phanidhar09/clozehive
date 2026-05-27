"""Shopping Check endpoints — in-store buy/skip advisor."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status, Query
from pydantic import BaseModel

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.services import shopping_check_service
from app.services.upload_service import delete_upload, read_validated_image, persist_upload

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
