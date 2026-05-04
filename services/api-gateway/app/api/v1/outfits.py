"""Saved outfit routes + AI outfit analysis endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.closet import ClosetItem, Outfit
from app.repositories.user_repo import UserRepository
from app.schemas.outfit_ai import AnalyzeOutfitRequest, AnalyzeOutfitResponse
from app.services import outfit_ai_service

router = APIRouter(prefix="/outfits", tags=["Outfits"])
logger = get_logger("outfits.routes")


# ── Save outfit ────────────────────────────────────────────────────────────────

class OutfitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    item_ids: list[str] = Field(..., min_length=1)
    occasion: str = Field(..., max_length=100)
    notes: str | None = Field(None, max_length=500)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_outfit(body: OutfitCreate, user_id: CurrentUser, session: DbSession):
    outfit = Outfit(
        user_id=UUID(user_id),
        name=body.name,
        item_ids=body.item_ids,
        occasion=body.occasion,
        explanation=body.notes,
    )
    session.add(outfit)
    await session.commit()
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

    # Resolve user personalization profile.
    user_obj = await UserRepository(session).get(uid)
    profile: dict | None = None
    if user_obj:
        raw_profile = {
            "body_profile":  user_obj.body_profile,
            "style_profile": user_obj.style_profile,
            "preferences":   user_obj.preferences,
        }
        profile = {k: v for k, v in raw_profile.items() if v} or None

    logger.info(
        "outfit_analyze_request",
        user_id=str(uid),
        item_count=len(items_for_ai),
        occasion=body.occasion,
    )

    data = await outfit_ai_service.analyze_outfit(
        items_for_ai,
        body.occasion,
        body.weather,
        body.temperature,
        user_profile=profile,
    )
    return data
