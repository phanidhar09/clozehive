"""Saved outfit routes + AI outfit analysis endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.models.closet import ClosetItem, Outfit
from app.services.style_profile_context import load_merged_user_profile_for_ai
from app.schemas.outfit_ai import AnalyzeOutfitRequest, AnalyzeOutfitResponse
from app.services import outfit_ai_service
from app.services.weather_service import get_weather_by_city

router = APIRouter(prefix="/outfits", tags=["Outfits"])
logger = get_logger("outfits.routes")


# ── List saved outfits ─────────────────────────────────────────────────────────

@router.get("/")
async def list_outfits(user_id: CurrentUser, session: DbSession):
    result = await session.execute(
        select(Outfit)
        .where(Outfit.user_id == UUID(user_id))
        .order_by(desc(Outfit.created_at))
    )
    outfits = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "item_ids": o.item_ids or [],
            "occasion": o.occasion or "",
            "ai_explanation": o.explanation or "",
            "style_score": o.style_score,
            "is_saved": True,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in outfits
    ]


# ── Save outfit ────────────────────────────────────────────────────────────────

class OutfitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    item_ids: list[str] = Field(..., min_length=1)
    occasion: str = Field(..., max_length=100)
    notes: str | None = Field(None, max_length=500)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_outfit(body: OutfitCreate, user_id: CurrentUser, session: DbSession):
    uid = UUID(user_id)
    item_uuids: list[UUID] = []
    for raw_id in body.item_ids:
        try:
            item_uuids.append(UUID(raw_id))
        except ValueError:
            raise BadRequestError(f"Invalid closet item id: {raw_id}")

    unique_ids = set(item_uuids)
    owned = await session.execute(
        select(ClosetItem.id).where(
            ClosetItem.user_id == uid,
            ClosetItem.id.in_(unique_ids),
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    found = {row[0] for row in owned.all()}
    if found != unique_ids:
        raise BadRequestError(
            "One or more items were not found, are archived, or do not belong to your closet."
        )

    outfit = Outfit(
        user_id=uid,
        name=body.name,
        item_ids=body.item_ids,
        occasion=body.occasion,
        explanation=body.notes,
    )
    session.add(outfit)
    await session.flush()
    await session.refresh(outfit)
    return {
        "id": str(outfit.id),
        "name": outfit.name,
        "item_ids": outfit.item_ids or [],
        "occasion": outfit.occasion or "",
        "ai_explanation": outfit.explanation or "",
        "style_score": outfit.style_score,
        "is_saved": True,
    }


# ── AI outfit analysis ─────────────────────────────────────────────────────────

@router.post("/generate", response_model=AnalyzeOutfitResponse)
async def analyze_outfit(body: AnalyzeOutfitRequest, user_id: CurrentUser, session: DbSession):
    """
    Analyse a specific outfit combination the user built in the Outfit Builder.

    Accepts a list of closet item IDs (the items dragged onto the canvas), plus
    occasion / weather context. Returns a detailed matching score (0–100) broken
    down across six weighted factors, along with improvements, issues, styling
    tips, and a plain-English reasoning paragraph.

    Scoring weights:
      Color Compatibility  25%
      Occasion Match       25%
      Fit & Size Alignment 20%
      Style Consistency    15%
      Weather Suitability  10%
      User Preference       5%
    """
    uid = UUID(user_id)

    # Fetch full item details for the selected IDs (owner-scoped, not archived).
    item_uuids: list[UUID] = []
    for raw_id in body.item_ids:
        try:
            item_uuids.append(UUID(raw_id))
        except ValueError:
            pass

    result = await session.execute(
        select(ClosetItem).where(
            ClosetItem.user_id == uid,
            ClosetItem.id.in_(item_uuids),
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    db_items = result.scalars().all()

    items_for_ai = [
        {
            "id":         str(item.id),
            "name":       item.name,
            "category":   item.category,
            "color":      item.color or "",
            "fabric":     item.fabric or "",
            "pattern":    item.pattern or "",
            "season":     item.season or "",
            "occasion":   item.occasion or [],
            "size":       item.size or "",
            "brand":      item.brand or "",
            "tags":       item.tags or [],
            "wear_count": item.wear_count,
        }
        for item in db_items
    ]

    merged = await load_merged_user_profile_for_ai(session, uid, None)
    profile: dict | None = merged if merged else None

    # Auto-fetch real weather when a location is provided.
    effective_weather = body.weather
    effective_temp = body.temperature
    if body.location:
        try:
            wx = await get_weather_by_city(body.location)
            effective_weather = wx.get("condition", effective_weather)
            effective_temp = wx.get("temp_c", effective_temp)
        except Exception:
            pass

    logger.info(
        "outfit_analyze_request",
        user_id=str(uid),
        item_count=len(items_for_ai),
        occasion=body.occasion,
        location=body.location,
        weather=effective_weather,
    )

    data = await outfit_ai_service.analyze_outfit(
        items_for_ai,
        body.occasion,
        effective_weather,
        effective_temp,
        user_profile=profile,
    )
    return data
