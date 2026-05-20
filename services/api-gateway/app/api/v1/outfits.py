"""Saved outfit routes + AI outfit analysis endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger

def _ws_push(user_id: str, data: dict) -> None:
    """Fire-and-forget WebSocket push — never raises."""
    try:
        import asyncio
        from app.api.v1.ws import manager as _ws_manager
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_ws_manager.broadcast_to_user(user_id, data))
    except Exception:
        pass
from app.models.closet import ClosetItem, Outfit
from app.services.style_profile_context import load_merged_user_profile_for_ai
from app.schemas.outfit_ai import AnalyzeOutfitRequest, AnalyzeOutfitResponse
from app.services import outfit_ai_service
from app.services.weather_service import get_weather_by_city
from app.services.fashion_rag_service import get_fashion_context_for_prompt
from app.services.outfit_history_service import (
    get_outfit_history_for_prompt,
    save_outfit_history,
)
from app.services.purchase_gap_service import detect_and_save_gaps

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
async def analyze_outfit(body: AnalyzeOutfitRequest, user_id: CurrentUser, session: DbSession, background_tasks: BackgroundTasks):
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

    # Build RAG context: fashion knowledge + past outfit history (best-effort)
    rag_parts: list[str] = []
    try:
        fashion_ctx = await get_fashion_context_for_prompt(session, f"{body.occasion} outfit {effective_weather}", limit=2)
        if fashion_ctx:
            rag_parts.append(fashion_ctx)
    except Exception:
        pass
    try:
        history_ctx = await get_outfit_history_for_prompt(session, user_id, body.occasion, effective_weather or "", limit=2)
        if history_ctx:
            rag_parts.append(history_ctx)
    except Exception:
        pass
    rag_context = "\n\n".join(rag_parts) or None

    data = await outfit_ai_service.analyze_outfit(
        items_for_ai,
        body.occasion,
        effective_weather,
        effective_temp,
        user_profile=profile,
        rag_context=rag_context,
    )

    # ── Suggest complementary pairings from the rest of the user's closet ────
    # Fetch all non-archived items the user owns, excluding the ones already on
    # the canvas, capped at 50 rows so the AI prompt stays compact.
    try:
        remaining_result = await session.execute(
            select(ClosetItem).where(
                ClosetItem.user_id == uid,
                ClosetItem.id.not_in(set(item_uuids)),
                ClosetItem.is_archived == False,  # noqa: E712
            ).limit(50)
        )
        remaining_db_items = remaining_result.scalars().all()

        remaining_for_ai = [
            {
                "id":       str(it.id),
                "name":     it.name,
                "category": it.category,
                "color":    it.color or "",
                "fabric":   it.fabric or "",
                "pattern":  it.pattern or "",
                "season":   it.season or "",
                "occasion": it.occasion or [],
                "brand":    it.brand or "",
            }
            for it in remaining_db_items
        ]
        remaining_map = {str(it.id): it for it in remaining_db_items}

        raw_suggestions = await outfit_ai_service.suggest_pairings_from_closet(
            items_for_ai,
            remaining_for_ai,
            body.occasion,
            effective_weather or "",
        )

        hydrated: list[dict] = []
        for s in raw_suggestions:
            item_id = str(s.get("id", ""))
            db_item = remaining_map.get(item_id)
            if db_item:
                hydrated.append({
                    "id":        item_id,
                    "name":      db_item.name,
                    "category":  db_item.category,
                    "color":     db_item.color,
                    "image_url": db_item.image_url,
                    "brand":     db_item.brand,
                    "reason":    s.get("reason", ""),
                })
        data["suggested_pairings"] = hydrated
    except Exception as exc:
        logger.warning("outfit_suggest_pairings_route_failed", error=str(exc))
        data.setdefault("suggested_pairings", [])

    # Persist outfit history and detect purchase gaps in background
    outfit_data = data.get("outfit", {})
    missing_pieces = data.get("missing_pieces", [])
    score = outfit_data.get("matching_score")
    reasoning = outfit_data.get("reasoning") or outfit_data.get("why_it_works")
    improvements = (outfit_data.get("recommendations") or {}).get("improvements", [])
    item_names = [i.get("name", "") for i in items_for_ai]

    background_tasks.add_task(
        _save_outfit_history_and_gaps,
        user_id=user_id,
        occasion=body.occasion,
        weather=effective_weather or "",
        item_ids=[str(i.get("id", "")) for i in items_for_ai],
        item_names=item_names,
        score=score,
        reasoning=reasoning,
        improvements=improvements,
        missing_pieces=missing_pieces,
        closet_items=items_for_ai,
    )

    # Real-time push: notify open browser tabs that analysis finished
    outfit_score = (data.get("outfit") or {}).get("matching_score")
    background_tasks.add_task(_ws_push, user_id, {
        "type": "notification",
        "channel": "ai",
        "data": {"event": "analysis_complete", "score": outfit_score, "occasion": body.occasion},
    })

    return data


async def _save_outfit_history_and_gaps(
    user_id: str,
    occasion: str,
    weather: str,
    item_ids: list[str],
    item_names: list[str],
    score: int | None,
    reasoning: str | None,
    improvements: list[str],
    missing_pieces: list[str],
    closet_items: list[dict],
) -> None:
    """Background task: save outfit history and detect purchase gaps."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as bg_session:
        try:
            await save_outfit_history(
                bg_session,
                user_id=user_id,
                occasion=occasion,
                weather=weather,
                selected_item_ids=item_ids,
                item_names=item_names,
                matching_score=score,
                recommendation_text=reasoning,
                improvement_tips=improvements,
            )
            await detect_and_save_gaps(
                bg_session,
                user_id=user_id,
                closet_items=closet_items,
                outfit_missing_pieces=missing_pieces,
                occasion=occasion,
            )
            await bg_session.commit()
        except Exception as exc:
            await bg_session.rollback()
            logger.warning("outfit_background_task_failed", error=str(exc))
