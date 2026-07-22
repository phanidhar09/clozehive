"""Daily FANI nudges — one proactive styling message per user per day.

Generated lazily on the first request to ``/ai-chat/nudges/today`` per
calendar date. The nudge type is chosen from a small priority hierarchy based
on what's actionable for *this* user *today*:

  calendar_prep > festival > weather_outfit > new_arrival > forgotten_gem
  > unworn_pick > generic

A short LLM call turns the chosen context into a one-sentence FANI message.
If the LLM call fails or the user has no actionable context, we return
``None`` so the UI hides the surface gracefully.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.intelligence.services import ai_service, festival_calendar, festival_discovery, model_router
from app.api.v1.intelligence.services.model_router import Task
from app.api.v1.travel.services import weather_service
from app.core.analytics import LLMTelemetry
from app.core.logging import get_logger
from app.models.ai_chat import DailyNudge
from app.models.closet import ClosetItem
from app.models.trips import Trip

logger = get_logger("daily_nudges")

# Items uploaded within this window count as "new arrivals" for the nudge.
NEW_ARRIVAL_WINDOW_DAYS = 5
# Trips starting within this window trigger a packing-prep nudge.
TRIP_PREP_WINDOW_DAYS = 3
# A user needs at least this many unworn items before we suggest they style one.
UNWORN_MIN_ITEMS = 4
# An item worn before but untouched for this long is a "forgotten gem" to revive.
# Kept in step with AnalyticsService._FORGOTTEN_DAYS so the two surfaces agree.
FORGOTTEN_GEM_DAYS = 60


_NUDGE_SYSTEM_PROMPT = (
    "You are FANI, ClozeHive's personal AI stylist. Write ONE warm, specific, "
    "actionable nudge for the user — 1 short sentence, max 22 words. "
    "Reference the supplied context concretely (the weather, the new item, the "
    "trip, etc.). End with a gentle call to action that fits naturally — never "
    "robotic CTAs like 'Click here'. No emojis unless one feels essential. "
    "Output the sentence only, no preamble, no quotes."
)


# ─────────────────────────────────────────────────────────────────────────────
# Context gathering
# ─────────────────────────────────────────────────────────────────────────────


async def _upcoming_trip(session: AsyncSession, user_id: UUID, today: date) -> Trip | None:
    horizon = today + timedelta(days=TRIP_PREP_WINDOW_DAYS)
    result = await session.execute(
        select(Trip)
        .where(
            Trip.user_id == user_id,
            Trip.start_date >= today,
            Trip.start_date <= horizon,
        )
        .order_by(Trip.start_date.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _recent_new_arrival(session: AsyncSession, user_id: UUID, today: date) -> ClosetItem | None:
    cutoff = datetime.combine(today - timedelta(days=NEW_ARRIVAL_WINDOW_DAYS), datetime.min.time())
    result = await session.execute(
        select(ClosetItem)
        .where(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
            ClosetItem.created_at >= cutoff,
            ClosetItem.wear_count == 0,
        )
        .order_by(ClosetItem.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _unworn_pick(session: AsyncSession, user_id: UUID) -> ClosetItem | None:
    # Count first — only nudge when there's a meaningful backlog of unworn items.
    count_result = await session.execute(
        select(func.count(ClosetItem.id)).where(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
            ClosetItem.wear_count == 0,
        )
    )
    count = int(count_result.scalar() or 0)
    if count < UNWORN_MIN_ITEMS:
        return None

    result = await session.execute(
        select(ClosetItem)
        .where(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
            ClosetItem.wear_count == 0,
        )
        .order_by(func.random())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _forgotten_gem(session: AsyncSession, user_id: UUID, today: date) -> ClosetItem | None:
    """A previously-worn item gone quiet for a while — the strongest revival hook.

    Unlike ``_unworn_pick`` (never-worn backlog), a gem was *loved* and then
    forgotten; reviving it is delightful and rewards owning, not buying. Rank by
    investment (price) first so an expensive, neglected piece surfaces ahead of a
    cheap one, then by how long it's been gone.
    """
    cutoff = today - timedelta(days=FORGOTTEN_GEM_DAYS)
    result = await session.execute(
        select(ClosetItem)
        .where(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
            ClosetItem.availability == "available",
            ClosetItem.condition != "damaged",
            ClosetItem.wear_count > 0,
            ClosetItem.last_worn.is_not(None),
            ClosetItem.last_worn <= cutoff,
        )
        .order_by(ClosetItem.price.desc().nullslast(), ClosetItem.last_worn.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _resolve_user_weather(session: AsyncSession, user_id: UUID) -> dict[str, Any] | None:
    try:
        user = await UserRepository(session).get(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("nudge_user_load_failed", error=str(exc))
        return None
    if not user:
        return None
    permissions = getattr(user, "permissions", None)
    if not isinstance(permissions, dict) or not permissions.get("location"):
        return None
    coords = permissions.get("location_coords")
    label = permissions.get("location_label")
    try:
        if isinstance(coords, dict) and coords.get("lat") is not None:
            return await weather_service.get_current_weather(float(coords["lat"]), float(coords["lon"]), label)
        if label:
            return await weather_service.get_weather_by_city(str(label))
    except Exception as exc:  # noqa: BLE001
        logger.warning("nudge_weather_failed", error=str(exc))
    return None


async def _resolve_home_location_label(session: AsyncSession, user_id: UUID) -> str | None:
    """Return the user's saved location label (e.g. 'Mumbai, India'), if any.

    Mirrors ``_resolve_user_weather``'s permission read but only needs the label
    so we can infer a country for festival lookups.
    """
    try:
        user = await UserRepository(session).get(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("nudge_home_location_failed", error=str(exc))
        return None
    if not user:
        return None
    permissions = getattr(user, "permissions", None)
    if not isinstance(permissions, dict):
        return None
    label = permissions.get("location_label")
    return str(label) if label else None


def _weather_is_noteworthy(weather: dict[str, Any]) -> bool:
    """Only weather nudges when conditions actually warrant outfit attention."""
    try:
        temp = float(weather.get("temp_c", 18))
    except (TypeError, ValueError):
        temp = 18.0
    cond = str(weather.get("condition") or "").lower()
    if temp < 8 or temp > 28:
        return True
    if any(k in cond for k in ("rain", "snow", "storm", "thunder", "wind")):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Nudge composition
# ─────────────────────────────────────────────────────────────────────────────


async def _llm_nudge(context_text: str) -> str:
    """Ask FANI to phrase the nudge. Returns "" on failure."""
    try:
        decision = model_router.for_task(Task.NUDGES_DAILY, max_tokens=120)
        text = await ai_service.chat(
            messages=[{"role": "user", "content": context_text}],
            system_prompt=_NUDGE_SYSTEM_PROMPT,
            model=decision.model,
            max_tokens=decision.max_tokens,
            temperature=decision.temperature,
            telemetry=LLMTelemetry(
                operation="nudges.daily",
                tier=decision.tier.value,
                route_reasons=decision.reasons,
            ),
        )
        return (text or "").strip().strip('"').strip("'")
    except Exception as exc:  # noqa: BLE001
        logger.warning("nudge_llm_failed", error=str(exc))
        return ""


async def _compose_nudge(session: AsyncSession, user_id: UUID, today: date) -> tuple[str, str, dict[str, Any]] | None:
    """Pick a nudge type, gather context, and ask the LLM to phrase it.

    Returns ``(message, nudge_type, payload)`` or ``None`` when nothing
    actionable is available.
    """
    # 1. Trip prep — highest priority, packing is time-sensitive. If a festival
    #    falls at the destination during the trip (static calendar, or live web
    #    discovery for the long tail), fold it into the prep nudge.
    trip = await _upcoming_trip(session, user_id, today)
    if trip:
        days_until = (trip.start_date - today).days
        payload: dict[str, Any] = {
            "trip_id": str(trip.id),
            "destination": trip.destination,
            "days_until": days_until,
        }
        base_ctx = (
            f"The user is leaving for {trip.destination} in {days_until} day(s) "
            f"({trip.start_date.isoformat()} → {trip.end_date.isoformat()}). "
        )
        fest_ctx = ""
        try:
            fest_result = await festival_discovery.get_trip_festivals(trip.destination, trip.start_date, trip.end_date)
            fest_ctx = festival_discovery.nudge_festival_context(fest_result)
            if fest_result["source"] == "static":
                f = fest_result["festivals"][0]
                payload["festival"] = {"name": f["name"], "date": f["date"]}
        except Exception as exc:  # noqa: BLE001 — festival layer is best-effort
            logger.warning("nudge_festival_failed", error=str(exc))
        ctx = base_ctx + (fest_ctx or "Suggest opening the trip packing plan today so nothing is rushed.")
        message = await _llm_nudge(ctx)
        if message:
            return (message, "calendar_prep", payload)

    # 2. Festival at home — a festival today or within the lookahead window at the
    #    user's saved location. Time-sensitive and delightful, so it ranks high.
    home_label = await _resolve_home_location_label(session, user_id)
    home_country = festival_calendar.infer_country(home_label)
    upcoming_fest = festival_calendar.next_festival(home_country, today)
    if upcoming_fest:
        occ_date, fest = upcoming_fest
        days_away = (occ_date - today).days
        when = "today" if days_away == 0 else f"in {days_away} day(s)"
        ctx = (
            f"{fest['name']} {fest['emoji']} is {when} ({occ_date.isoformat()}). "
            f"Dress guidance: {fest['dress']} "
            "Suggest the user let FANI build a festive outfit from their closet for it."
        )
        message = await _llm_nudge(ctx)
        if message:
            return (
                message,
                "festival",
                {
                    "festival": fest["name"],
                    "emoji": fest["emoji"],
                    "date": occ_date.isoformat(),
                    "days_away": days_away,
                },
            )

    # 3. Weather — only when conditions actually require an outfit decision.
    weather = await _resolve_user_weather(session, user_id)
    if weather and _weather_is_noteworthy(weather):
        ctx = (
            f"Today's weather at {weather.get('location_label') or 'their location'}: "
            f"{weather.get('condition')}, "
            f"{weather.get('temp_c')}°C (feels like {weather.get('feels_like_c')}°C). "
            "Suggest the user open FANI to build a wardrobe-grounded outfit for it."
        )
        message = await _llm_nudge(ctx)
        if message:
            return (
                message,
                "weather_outfit",
                {
                    "condition": weather.get("condition"),
                    "temp_c": weather.get("temp_c"),
                    "location": weather.get("location_label"),
                },
            )

    # 4. New arrival — encourage styling a freshly-added item.
    new_item = await _recent_new_arrival(session, user_id, today)
    if new_item:
        ctx = (
            f"The user recently added a new piece: '{new_item.name}' "
            f"({new_item.category}{', ' + new_item.color if new_item.color else ''}). "
            "It hasn't been styled into an outfit yet. Suggest building one around it."
        )
        message = await _llm_nudge(ctx)
        if message:
            return (
                message,
                "new_arrival",
                {
                    "item_id": str(new_item.id),
                    "item_name": new_item.name,
                    "category": new_item.category,
                },
            )

    # 5. Forgotten gem — revive a once-loved piece that's gone quiet. Ranks above
    #    the never-worn nudge: bringing back something they chose to wear is a
    #    stronger, more delightful hook than highlighting a never-touched item.
    gem = await _forgotten_gem(session, user_id, today)
    if gem and gem.last_worn:
        days_since = (today - gem.last_worn).days
        ctx = (
            f"The user owns '{gem.name}' ({gem.category}"
            f"{', ' + gem.color if gem.color else ''}) but hasn't worn it in "
            f"{days_since} days, though they've worn it {gem.wear_count} times before. "
            "Warmly suggest letting FANI build a fresh outfit to bring it back into rotation."
        )
        message = await _llm_nudge(ctx)
        if message:
            return (
                message,
                "forgotten_gem",
                {
                    "item_id": str(gem.id),
                    "item_name": gem.name,
                    "category": gem.category,
                    "days_since_worn": days_since,
                    "wear_count": gem.wear_count,
                },
            )

    # 6. Unworn pick — gentle "you have things you haven't worn" nudge.
    unworn = await _unworn_pick(session, user_id)
    if unworn:
        ctx = (
            f"The user has unworn items collecting dust. Highlight one: "
            f"'{unworn.name}' ({unworn.category}"
            f"{', ' + unworn.color if unworn.color else ''}). "
            "Suggest letting FANI work it into today's look."
        )
        message = await _llm_nudge(ctx)
        if message:
            return (
                message,
                "unworn_pick",
                {
                    "item_id": str(unworn.id),
                    "item_name": unworn.name,
                    "category": unworn.category,
                },
            )

    # 7. Nothing actionable — skip; don't bug the user with filler.
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_or_generate_today_nudge(
    session: AsyncSession, user_id: UUID, today: date | None = None
) -> DailyNudge | None:
    """Return today's nudge, generating it on the first call of the day."""
    today = today or date.today()

    # Already generated? Return it (even if dismissed — UI decides).
    existing = await session.execute(
        select(DailyNudge).where(and_(DailyNudge.user_id == user_id, DailyNudge.nudge_date == today))
    )
    nudge = existing.scalar_one_or_none()
    if nudge:
        return nudge

    composed = await _compose_nudge(session, user_id, today)
    if not composed:
        return None

    message, nudge_type, payload = composed
    nudge = DailyNudge(
        user_id=user_id,
        nudge_date=today,
        message=message,
        nudge_type=nudge_type,
        payload=payload,
    )
    session.add(nudge)
    try:
        await session.flush()
    except IntegrityError:
        # Race with a concurrent request — re-read the row that won.
        await session.rollback()
        existing = await session.execute(
            select(DailyNudge).where(and_(DailyNudge.user_id == user_id, DailyNudge.nudge_date == today))
        )
        return existing.scalar_one_or_none()
    await session.refresh(nudge)
    logger.info(
        "nudge_generated",
        user_id=str(user_id),
        nudge_type=nudge_type,
        message_len=len(message),
    )
    return nudge


def serialize_nudge(nudge: DailyNudge) -> dict[str, Any]:
    return {
        "id": str(nudge.id),
        "nudge_date": nudge.nudge_date.isoformat(),
        "message": nudge.message,
        "nudge_type": nudge.nudge_type,
        "payload": nudge.payload or {},
        "dismissed": nudge.dismissed,
        "created_at": nudge.created_at.isoformat(),
    }
