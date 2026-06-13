"""Weekly outfit planner routes — a persisted, weather-aware 7-day calendar.

FANI generates the week in one AI call (see weekly_planner_service); users can
override single days, clear them, and mark a day as worn — which feeds
wear_count / last_worn and the outfit-history RAG corpus.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.identity.services.style_profile_context import load_merged_user_profile_for_ai
from app.api.v1.travel.services import weather_service
from app.api.v1.wardrobe.services import weekly_planner_service
from app.api.v1.wardrobe.services.outfit_history_service import save_outfit_history_background
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.models.closet import ClosetItem, PlannedOutfit

router = APIRouter(prefix="/planner", tags=["Weekly Planner"])
logger = get_logger("planner.routes")

_MAX_PLAN_DAYS = 7
_CLOSET_PROMPT_LIMIT = 120


# ── Schemas ────────────────────────────────────────────────────────────────────


class DayWeatherIn(BaseModel):
    date: date
    condition: str = Field("", max_length=100)
    temp_high: float | None = None
    temp_low: float | None = None
    occasion: str | None = Field(None, max_length=100)


class GeneratePlanRequest(BaseModel):
    start_date: date | None = None
    # Client-supplied forecast (the SPA already fetches Open-Meteo). When absent
    # the server falls back to its own weather lookup for `location`.
    days: list[DayWeatherIn] | None = Field(None, max_length=_MAX_PLAN_DAYS)
    location: str | None = Field(None, max_length=120)


class UpdateDayRequest(BaseModel):
    item_ids: list[str] = Field(..., min_length=1, max_length=12)
    occasion: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _day_payload(row: PlannedOutfit, items_by_id: dict[str, ClosetItem]) -> dict:
    items = []
    for raw_id in row.item_ids or []:
        item = items_by_id.get(raw_id)
        if item:
            items.append(
                {
                    "id": str(item.id),
                    "name": item.name,
                    "category": item.category,
                    "color": item.color,
                    "brand": item.brand,
                    "image_url": item.processed_image_url or item.image_url or item.original_image_url,
                }
            )
    return {
        "plan_date": row.plan_date.isoformat(),
        "occasion": row.occasion or "",
        "items": items,
        "weather_condition": row.weather_condition,
        "temp_high": float(row.temp_high) if row.temp_high is not None else None,
        "temp_low": float(row.temp_low) if row.temp_low is not None else None,
        "reasoning": row.reasoning or "",
        "source": row.source,
        "is_worn": row.is_worn,
    }


async def _hydrated_week(session: DbSession, uid: UUID, start: date, end: date) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(PlannedOutfit)
                .where(
                    PlannedOutfit.user_id == uid,
                    PlannedOutfit.plan_date >= start,
                    PlannedOutfit.plan_date <= end,
                )
                .order_by(PlannedOutfit.plan_date)
            )
        )
        .scalars()
        .all()
    )
    all_ids: set[UUID] = set()
    for row in rows:
        for raw_id in row.item_ids or []:
            try:
                all_ids.add(UUID(raw_id))
            except ValueError:
                pass
    items_by_id: dict[str, ClosetItem] = {}
    if all_ids:
        item_rows = await session.execute(
            select(ClosetItem).where(ClosetItem.user_id == uid, ClosetItem.id.in_(all_ids))
        )
        items_by_id = {str(i.id): i for i in item_rows.scalars().all()}
    return [_day_payload(r, items_by_id) for r in rows]


async def _load_closet_for_ai(session: DbSession, uid: UUID) -> list[dict]:
    rows = await session.execute(
        select(ClosetItem)
        .where(
            ClosetItem.user_id == uid,
            ClosetItem.is_archived == False,  # noqa: E712
            ClosetItem.availability == "available",
        )
        .order_by(ClosetItem.wear_count.asc())
        .limit(_CLOSET_PROMPT_LIMIT)
    )
    return [
        {
            "id": str(i.id),
            "name": i.name,
            "category": i.category,
            "color": i.color or "",
            "fabric": i.fabric or "",
            "pattern": i.pattern or "",
            "season": i.season or [],
            "occasion": i.occasion or [],
            "size": i.size or "",
            "brand": i.brand or "",
            "tags": i.tags or [],
            "wear_count": i.wear_count,
            "last_worn": i.last_worn.isoformat() if i.last_worn else None,
        }
        for i in rows.scalars().all()
    ]


async def _resolve_forecast_days(body: GeneratePlanRequest, session: DbSession, user_id: str) -> list[dict]:
    if body.days:
        return [
            {
                "date": d.date.isoformat(),
                "condition": d.condition,
                "temp_high": d.temp_high,
                "temp_low": d.temp_low,
                "occasion": d.occasion,
            }
            for d in sorted(body.days, key=lambda d: d.date)
        ]

    start = body.start_date or date.today()
    end = start + timedelta(days=_MAX_PLAN_DAYS - 1)
    location = body.location
    if not location:
        user = await UserRepository(session).get(UUID(user_id))
        permissions = user.permissions if user else None
        if isinstance(permissions, dict):
            location = permissions.get("location_label")
    if location:
        try:
            return await weather_service.fetch_weather_async(location, start.isoformat(), end.isoformat())
        except Exception as exc:
            logger.warning("planner_weather_lookup_failed", error=str(exc), location=location)
    # No location anywhere — plan by occasion only.
    return [
        {"date": d.isoformat(), "condition": "", "temp_high": None, "temp_low": None}
        for d in weekly_planner_service.default_week_dates(start)
    ]


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/week")
async def get_week(user_id: CurrentUser, session: DbSession, start: date | None = None):
    """The persisted plan for the 7 days beginning at ``start`` (default today)."""
    first = start or date.today()
    days = await _hydrated_week(session, UUID(user_id), first, first + timedelta(days=_MAX_PLAN_DAYS - 1))
    return {"start_date": first.isoformat(), "days": days}


@router.post("/generate", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def generate_week(
    request: Request,
    body: GeneratePlanRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """Generate (or regenerate) the week. Days already marked worn are kept."""
    uid = UUID(user_id)
    forecast_days = await _resolve_forecast_days(body, session, user_id)
    if not forecast_days:
        raise BadRequestError("No days to plan.")
    forecast_days = forecast_days[:_MAX_PLAN_DAYS]

    closet_items = await _load_closet_for_ai(session, uid)
    if not closet_items:
        raise BadRequestError("Add closet items before generating a weekly plan.")

    plan_dates = [date.fromisoformat(str(d["date"])) for d in forecast_days]
    existing_rows = (
        (
            await session.execute(
                select(PlannedOutfit).where(PlannedOutfit.user_id == uid, PlannedOutfit.plan_date.in_(plan_dates))
            )
        )
        .scalars()
        .all()
    )
    existing = {r.plan_date: r for r in existing_rows}

    # Keep worn days untouched — replanning a day that already happened is noise.
    plannable = []
    for d in forecast_days:
        row = existing.get(date.fromisoformat(str(d["date"])))
        if row is None or not row.is_worn:
            plannable.append(d)

    cutoff = date.today() - timedelta(days=7)
    recently_worn = [
        i["name"] for i in closet_items if i.get("last_worn") and date.fromisoformat(i["last_worn"]) >= cutoff
    ]

    profile = await load_merged_user_profile_for_ai(session, uid, None)
    plan = await weekly_planner_service.generate_week_plan(
        closet_items, plannable, user_profile=profile or None, recently_worn_names=recently_worn
    )

    weather_by_date = {str(d["date"]): d for d in forecast_days}
    for entry in plan:
        day = date.fromisoformat(str(entry["date"]))
        wx = weather_by_date.get(str(entry["date"]), {})
        row = existing.get(day)
        if row is None:
            row = PlannedOutfit(user_id=uid, plan_date=day)
            session.add(row)
        row.item_ids = entry["item_ids"]
        row.occasion = entry["occasion"]
        row.reasoning = entry["reasoning"]
        row.source = "fani"
        row.is_worn = False
        row.weather_condition = str(wx.get("condition") or "") or None
        row.temp_high = wx.get("temp_high")
        row.temp_low = wx.get("temp_low")
    await session.flush()

    logger.info("weekly_plan_generated", user_id=user_id, days=len(plan))
    days = await _hydrated_week(session, uid, min(plan_dates), max(plan_dates))
    return {"start_date": min(plan_dates).isoformat(), "days": days}


@router.put("/{plan_date}")
async def set_day(plan_date: date, body: UpdateDayRequest, user_id: CurrentUser, session: DbSession):
    """Manually assign the outfit for one day (replaces any FANI pick)."""
    uid = UUID(user_id)
    item_uuids: list[UUID] = []
    for raw_id in body.item_ids:
        try:
            item_uuids.append(UUID(raw_id))
        except ValueError:
            raise BadRequestError(f"Invalid closet item id: {raw_id}")
    owned = await session.execute(
        select(ClosetItem.id).where(
            ClosetItem.user_id == uid,
            ClosetItem.id.in_(set(item_uuids)),
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    if {row[0] for row in owned.all()} != set(item_uuids):
        raise BadRequestError("One or more items were not found, are archived, or do not belong to your closet.")

    row = (
        await session.execute(
            select(PlannedOutfit).where(PlannedOutfit.user_id == uid, PlannedOutfit.plan_date == plan_date)
        )
    ).scalar_one_or_none()
    if row is None:
        row = PlannedOutfit(user_id=uid, plan_date=plan_date)
        session.add(row)
    row.item_ids = body.item_ids
    if body.occasion:
        row.occasion = body.occasion
    row.reasoning = body.notes or row.reasoning
    row.source = "manual"
    row.is_worn = False
    await session.flush()
    days = await _hydrated_week(session, uid, plan_date, plan_date)
    return days[0]


@router.delete("/{plan_date}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_day(plan_date: date, user_id: CurrentUser, session: DbSession):
    row = (
        await session.execute(
            select(PlannedOutfit).where(PlannedOutfit.user_id == UUID(user_id), PlannedOutfit.plan_date == plan_date)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("No plan exists for this date.")
    await session.delete(row)


@router.post("/{plan_date}/worn")
async def mark_worn(
    plan_date: date,
    user_id: CurrentUser,
    session: DbSession,
    background_tasks: BackgroundTasks,
):
    """Mark the day's outfit as worn: bumps wear_count / last_worn on each item
    and records the outfit in history (feeds FANI's RAG context)."""
    uid = UUID(user_id)
    row = (
        await session.execute(
            select(PlannedOutfit).where(PlannedOutfit.user_id == uid, PlannedOutfit.plan_date == plan_date)
        )
    ).scalar_one_or_none()
    if row is None or not row.item_ids:
        raise NotFoundError("No planned outfit exists for this date.")
    if row.is_worn:
        days = await _hydrated_week(session, uid, plan_date, plan_date)
        return days[0]

    item_uuids = []
    for raw_id in row.item_ids:
        try:
            item_uuids.append(UUID(raw_id))
        except ValueError:
            pass
    items = (
        (await session.execute(select(ClosetItem).where(ClosetItem.user_id == uid, ClosetItem.id.in_(item_uuids))))
        .scalars()
        .all()
    )
    for item in items:
        item.wear_count = (item.wear_count or 0) + 1
        if item.last_worn is None or item.last_worn < plan_date:
            item.last_worn = plan_date
    row.is_worn = True
    await session.flush()

    background_tasks.add_task(
        save_outfit_history_background,
        user_id=user_id,
        occasion=row.occasion or "casual",
        weather=row.weather_condition or "",
        selected_item_ids=[str(i.id) for i in items],
        item_names=[i.name for i in items],
        matching_score=None,
        recommendation_text=row.reasoning,
        improvement_tips=[],
    )

    days = await _hydrated_week(session, uid, plan_date, plan_date)
    return days[0]
