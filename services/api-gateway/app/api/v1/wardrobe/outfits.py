"""Saved outfit routes + AI outfit analysis endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import time
from uuid import UUID

_analyze_cache: dict[str, tuple[dict, float]] = {}
_ANALYZE_CACHE_TTL = 300  # 5 minutes

from fastapi import APIRouter, BackgroundTasks, Request, status
from app.core.rate_limit import limiter
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError
from app.core.constraint_priority import build_constraint_priority_block
from app.core.logging import get_logger
from app.models.closet import ClosetItem, Outfit
from app.api.v1.identity.services.style_profile_context import load_merged_user_profile_for_ai
from app.api.v1.wardrobe.schemas.outfit_ai import AnalyzeOutfitRequest, AnalyzeOutfitResponse
from app.api.v1.wardrobe.services import outfit_ai_service
from app.api.v1.travel.services.weather_service import get_weather_by_city
from app.api.v1.travel.services.location_intel_service import (
    build_location_context_block_async,
)
from app.api.v1.intelligence.services.fashion_rag_service import get_fashion_context_for_prompt
from app.api.v1.wardrobe.services.outfit_history_service import (
    get_outfit_history_for_prompt,
    save_outfit_history,
)
from app.core.embedding_service import generate_text_embedding, pgvector_cosine_search
from app.api.v1.intelligence.services.purchase_gap_service import detect_and_save_gaps


def _ws_push(user_id: str, data: dict) -> None:
    """Fire-and-forget WebSocket push — never raises."""
    try:
        from app.api.v1.platform.ws import manager as _ws_manager
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_ws_manager.broadcast_to_user(user_id, data))
    except Exception:
        pass


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

@router.post("/analyze", response_model=AnalyzeOutfitResponse)
@limiter.limit("20/minute")
async def analyze_outfit(request: Request, body: AnalyzeOutfitRequest, user_id: CurrentUser, session: DbSession, background_tasks: BackgroundTasks):
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
    location_context = await build_location_context_block_async(body.location or "", mode="daily")

    # Constraint priority — arbitrates location norms vs weather vs occasion vs
    # style when several layers are active (see app.core.constraint_priority).
    priority_block = build_constraint_priority_block(
        mandatory=bool(location_context),
        weather=bool(effective_weather),
        occasion=bool(body.occasion),
        style=bool(profile),
    )
    if priority_block:
        location_context = f"{priority_block}\n\n{location_context}" if location_context else priority_block

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

    _cache_key = hashlib.md5(
        (",".join(sorted(str(i) for i in item_uuids)) + "|" + body.occasion + "|" + (effective_weather or "")).encode()
    ).hexdigest()
    _now = time.monotonic()
    _cached = _analyze_cache.get(_cache_key)
    if _cached and (_now - _cached[1]) < _ANALYZE_CACHE_TTL:
        data = _cached[0]
    else:
        data = await outfit_ai_service.analyze_outfit(
            items_for_ai,
            body.occasion,
            effective_weather,
            effective_temp,
            user_profile=profile,
            rag_context=rag_context,
            location_context=location_context,
        )
        _analyze_cache[_cache_key] = (data, _now)
        if len(_analyze_cache) > 500:
            oldest = min(_analyze_cache, key=lambda k: _analyze_cache[k][1])
            del _analyze_cache[oldest]

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
        data["suggested_pairings_error"] = True

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


class ShuffleOutfitRequest(BaseModel):
    item_ids: list[str] = Field(..., min_items=1, description="Current outfit item IDs")
    occasion: str = "casual"
    seed_category: str | None = Field(None, description="Optional category to anchor first alternative (e.g. 'tops', 'bottoms')")
    location: str | None = None


@router.post("/shuffle")
@limiter.limit("15/minute")
async def shuffle_outfit(
    request: Request,
    body: ShuffleOutfitRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """Suggest 1–2 alternative outfit combinations from the user's closet."""
    uid = UUID(user_id)

    # Load current outfit items
    item_uuids = []
    for raw_id in body.item_ids:
        try:
            item_uuids.append(UUID(raw_id))
        except ValueError:
            pass

    current_rows = await session.execute(
        select(ClosetItem).where(
            ClosetItem.id.in_(item_uuids),
            ClosetItem.user_id == uid,
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    current_items = [
        {
            "id": str(r.id), "name": r.name, "category": r.category,
            "color": r.color or "", "fabric": r.fabric or "",
            "pattern": r.pattern or "", "occasion": r.occasion or [],
            "season": r.season or [], "tags": r.tags or [],
            "image_url": r.processed_image_url or r.image_url or r.original_image_url,
        }
        for r in current_rows.scalars().all()
    ]

    # Load the rest of the closet — RAG-filtered by occasion so the AI receives
    # the most relevant alternatives first; fall back to wear_count order.
    current_ids = {str(i) for i in item_uuids}
    weather_str = ""

    # Resolve weather first (needed for RAG query and AI prompt)
    if body.location:
        try:
            w = await get_weather_by_city(body.location)
            weather_str = w.get("condition", "") if w else ""
        except Exception:
            pass

    rag_query = f"outfit for {body.occasion} occasion weather:{weather_str or 'mild'}"
    embedding = await generate_text_embedding(rag_query)
    available: list[dict] = []
    if embedding:
        vector_rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=str(uid),
            limit=60,
            threshold=0.20,
            filter_archived=True,
        )
        available = [
            {
                "id": str(r["id"]), "name": r.get("name") or "",
                "category": r.get("category") or "", "color": r.get("color") or "",
                "fabric": r.get("fabric") or "", "pattern": r.get("pattern") or "",
                "occasion": r.get("occasion") or [], "season": r.get("season") or [],
                "tags": r.get("tags") or [],
                "image_url": r.get("processed_image_url") or r.get("image_url") or r.get("original_image_url"),
            }
            for r in vector_rows
            if str(r["id"]) not in current_ids
        ]

    if not available:
        # Fallback: wear_count order when no embeddings exist yet
        all_rows = await session.execute(
            select(ClosetItem)
            .where(ClosetItem.user_id == uid, ClosetItem.is_archived == False)  # noqa: E712
            .order_by(ClosetItem.wear_count.desc())
            .limit(80)
        )
        available = [
            {
                "id": str(r.id), "name": r.name, "category": r.category,
                "color": r.color or "", "fabric": r.fabric or "",
                "pattern": r.pattern or "", "occasion": r.occasion or [],
                "season": r.season or [], "tags": r.tags or [],
                "image_url": r.processed_image_url or r.image_url or r.original_image_url,
            }
            for r in all_rows.scalars().all()
            if str(r.id) not in current_ids
        ]

    # Fetch fashion knowledge + past outfit history in parallel for richer recommendations
    fashion_ctx, history_ctx = await asyncio.gather(
        get_fashion_context_for_prompt(session, rag_query),
        get_outfit_history_for_prompt(session, str(uid), body.occasion),
        return_exceptions=True,
    )
    fashion_context = fashion_ctx if isinstance(fashion_ctx, str) else ""
    history_context = history_ctx if isinstance(history_ctx, str) else ""

    # Always ground alternatives in the user's persisted style profile/summary.
    user_profile = await load_merged_user_profile_for_ai(session, uid, None)

    alternatives = await outfit_ai_service.shuffle_outfit(
        current_items=current_items,
        available_closet=available,
        occasion=body.occasion,
        weather=weather_str,
        seed_category=body.seed_category,
        fashion_context=fashion_context,
        history_context=history_context,
        user_profile=user_profile,
    )

    # Enrich alternatives with image_urls from full closet
    closet_map = {r["id"]: r for r in current_items + available}
    for alt in alternatives:
        enriched_items = []
        valid_ids = set(closet_map.keys())
        for it in alt.get("items") or []:
            if it.get("id") in valid_ids:
                full = closet_map[it["id"]]
                enriched_items.append({**it, "image_url": full.get("image_url")})
        alt["items"] = enriched_items

    return {"alternatives": alternatives}


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
