"""Daily FANI nudges — one proactive styling message per user per day.

Generated lazily on the first request to ``/ai-chat/nudges/today`` per
calendar date. The nudge type is chosen from a small priority hierarchy based
on what's actionable for *this* user *today*:

  calendar_prep  > weather_outfit  > new_arrival  > unworn_pick  > generic

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

from app.core.logging import get_logger
from app.models.ai_chat import DailyNudge
from app.models.closet import ClosetItem
from app.models.trips import Trip
from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.intelligence.services import ai_service
from app.api.v1.travel.services import weather_service

logger = get_logger("daily_nudges")

# Items uploaded within this window count as "new arrivals" for the nudge.
NEW_ARRIVAL_WINDOW_DAYS = 5
# Trips starting within this window trigger a packing-prep nudge.
TRIP_PREP_WINDOW_DAYS = 3
# A user needs at least this many unworn items before we suggest they style one.
UNWORN_MIN_ITEMS = 4


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


async def _recent_new_arrival(
    session: AsyncSession, user_id: UUID, today: date
) -> ClosetItem | None:
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


async def _resolve_user_weather(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
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
            return await weather_service.get_current_weather(
                float(coords["lat"]), float(coords["lon"]), label
            )
        if label:
            return await weather_service.get_weather_by_city(str(label))
    except Exception as exc:  # noqa: BLE001
        logger.warning("nudge_weather_failed", error=str(exc))
    return None


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
        text = await ai_service.chat(
            messages=[{"role": "user", "content": context_text}],
            system_prompt=_NUDGE_SYSTEM_PROMPT,
        )
        return (text or "").strip().strip('"').strip("'")
    except Exception as exc:  # noqa: BLE001
        logger.warning("nudge_llm_failed", error=str(exc))
        return ""


async def _compose_nudge(
    session: AsyncSession, user_id: UUID, today: date
) -> tuple[str, str, dict[str, Any]] | None:
    """Pick a nudge type, gather context, and ask the LLM to phrase it.

    Returns ``(message, nudge_type, payload)`` or ``None`` when nothing
    actionable is available.
    """
    # 1. Trip prep — highest priority, packing is time-sensitive.
    trip = await _upcoming_trip(session, user_id, today)
    if trip:
        days_until = (trip.start_date - today).days
        ctx = (
            f"The user is leaving for {trip.destination} in {days_until} day(s) "
            f"({trip.start_date.isoformat()} → {trip.end_date.isoformat()}). "
            "Suggest opening the trip packing plan today so nothing is rushed."
        )
        message = await _llm_nudge(ctx)
        if message:
            return (
                message,
                "calendar_prep",
                {
                    "trip_id": str(trip.id),
                    "destination": trip.destination,
                    "days_until": days_until,
                },
            )

    # 2. Weather — only when conditions actually require an outfit decision.
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

    # 3. New arrival — encourage styling a freshly-added item.
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

    # 4. Unworn pick — gentle "you have things you haven't worn" nudge.
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

    # 5. Nothing actionable — skip; don't bug the user with filler.
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
        select(DailyNudge).where(
            and_(DailyNudge.user_id == user_id, DailyNudge.nudge_date == today)
        )
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
            select(DailyNudge).where(
                and_(DailyNudge.user_id == user_id, DailyNudge.nudge_date == today)
            )
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
