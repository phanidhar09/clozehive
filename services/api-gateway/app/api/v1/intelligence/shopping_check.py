"""Shopping Check endpoints — in-store buy/skip advisor + closet match."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.api.v1.intelligence.services import shopping_check_service
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.upload_service import delete_upload, persist_upload, read_validated_image

router = APIRouter(prefix="/shopping", tags=["Shopping Check"])
logger = get_logger("shopping_check_api")


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
        image_url = await persist_upload(image_bytes, media_type, file.filename)
    except Exception as exc:
        logger.warning("shopping_image_persist_failed", error=str(exc))

    result = await shopping_check_service.analyze_shopping_item(
        image_bytes=image_bytes,
        media_type=media_type,
        user_id=user_id,
        session=session,
        image_url=image_url,
    )
    return result


class UrlCheckRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048, description="Product page URL")


@router.post("/check-url", status_code=status.HTTP_201_CREATED)
async def check_shopping_url(
    body: UrlCheckRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """
    Paste a product URL and get FANI's honest verdict against your closet.

    Pulls the product image from the page's Open Graph / JSON-LD metadata; if the
    page exposes none, falls back to a rendered screenshot through the existing
    vision pipeline. No scraper infrastructure — a single page fetch.

    Returns the same shape as ``/shopping/check`` plus source attribution
    (``source_url``, ``source_title``, ``source_brand``, ``source_price``) and
    ``url_check_count`` — how many product links this user has now checked (the
    repeat-paste retention/viral signal).
    """
    result = await shopping_check_service.analyze_shopping_item_from_url(
        url=body.url,
        user_id=user_id,
        session=session,
    )
    return result


class ShoppingEventRequest(BaseModel):
    event_type: str = Field(..., max_length=40, description="Funnel event, e.g. verdict_viewed")
    metadata: dict | None = None


@router.post("/{check_id}/event", status_code=status.HTTP_202_ACCEPTED)
async def log_shopping_event(
    check_id: UUID,
    body: ShoppingEventRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """Record a Shop with FANI funnel event (viewed / opened outfit / acted /
    pasted again). Best-effort instrumentation — unknown event types are ignored."""
    written = await shopping_check_service.record_shopping_event(
        session=session,
        user_id=user_id,
        event_type=body.event_type,
        check_id=str(check_id),
        metadata=body.metadata,
    )
    return {"recorded": written}


@router.post("/{check_id}/outfits", status_code=status.HTTP_200_OK)
async def build_outfits_for_check(
    check_id: UUID,
    user_id: CurrentUser,
    session: DbSession,
):
    """Ask 2 — "build the best outfits I could wear with this". Returns the top
    complete looks assembled from the user's own closet around the checked item,
    each with a 5-tier rating, a stylist note, and the items to compose visually.
    Required roles the closet can't fill are returned as ``missing_roles`` (the
    seam Ask 3 — gap detection — uses)."""
    result = await shopping_check_service.build_outfits_for_check(
        check_id=str(check_id),
        user_id=user_id,
        session=session,
    )
    if result is None:
        raise NotFoundError("Shopping check not found")
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
