"""Read-only tools for the travel packing advisor agent.

The anchor is :func:`_get_trip_plan`, which loads the **already-generated** packing
plan for a trip. As with the shopping advisor, that ordering is deliberate:
``packing_service.generate_packing_list`` is a grounded pipeline — every
"from_closet" pick is verified against the real closet, invented items are
downgraded to recommendations, and all sections are derived deterministically from
``day_plans_rich`` (the packing-hallucination-hardening work). The agent reads that
finished plan and never regenerates it, so it cannot reintroduce hallucinated items.

The other tools are the trip-varying research the fixed pipeline runs once up front
(weather, festivals, venue dress rules) plus the shared closet/knowledge lookups.
Exposing them as tools lets the model fetch only what a given follow-up needs — a
"will I be warm enough?" turn wants weather, a "temple dress code?" turn wants venue
rules, and neither needs the other.

Ownership: the trip id is a tool argument (the model reads it from context), so both
the trip and its plan are loaded filtered by ``user_id``. A wrong or invented id
returns "not found", never another user's trip.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intelligence.services import festival_discovery
from app.api.v1.intelligence.services.agents.loop import AgentTool
from app.api.v1.intelligence.services.agents.shopping_tools import fashion_knowledge_tool
from app.api.v1.intelligence.services.agents.wardrobe_tools import search_closet_tool
from app.api.v1.travel.services import venue_rules_service, weather_service
from app.core.logging import get_logger
from app.models.packing import PackingPlan
from app.models.trips import Trip

logger = get_logger("travel_tools")

# Per-day outfit lines are summarised, not dumped — the model needs the shape of
# the plan (what's worn each day, what's missing), not every attribute.
_MAX_DAYS_SUMMARISED = 14


def _summarise_day(day: dict[str, Any]) -> dict[str, Any]:
    """One day's plan flattened to occasion + the items it calls for."""
    items: list[str] = []
    owned = 0
    for outfit in day.get("outfits", []) or []:
        for item in outfit.get("items", []) or []:
            name = str(item.get("item_name") or "").strip()
            if not name:
                continue
            if str(item.get("source") or "") == "from_closet":
                owned += 1
                items.append(name)
            else:
                items.append(f"{name} (recommended)")
    return {
        "day_number": day.get("day_number"),
        "occasion": day.get("occasion") or day.get("summary"),
        "items": items[:10],
        "owned_item_count": owned,
    }


async def _get_trip_plan(session: AsyncSession, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Load the stored trip + its generated packing plan, scoped to the owner."""
    trip_id = str(args.get("trip_id") or "").strip()
    if not trip_id:
        return {"error": "trip_id is required"}

    try:
        trip_uuid = UUID(trip_id)
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        return {"error": "That trip could not be found."}

    trip = (
        await session.execute(select(Trip).where(Trip.id == trip_uuid, Trip.user_id == user_uuid))
    ).scalar_one_or_none()
    if trip is None:
        return {"error": "That trip could not be found."}

    plan = (
        await session.execute(
            select(PackingPlan).where(PackingPlan.trip_id == trip_uuid, PackingPlan.user_id == user_uuid)
        )
    ).scalar_one_or_none()

    trip_info: dict[str, Any] = {
        "destination": trip.destination,
        "start_date": trip.start_date.isoformat() if trip.start_date else None,
        "end_date": trip.end_date.isoformat() if trip.end_date else None,
        "purpose": trip.purpose,
        "trip_style": trip.trip_style,
        "bag_size": trip.bag_size,
        "activities": [a.get("name") for a in (trip.activities or []) if isinstance(a, dict) and a.get("name")],
    }

    if plan is None:
        # A trip with no generated plan yet — say so plainly rather than implying
        # an empty plan, so the model tells the user to generate one first.
        return {"trip": trip_info, "plan_status": "not_generated"}

    raw = plan.raw_result or {}
    return {
        "trip": trip_info,
        "plan_status": "generated",
        "weather_summary": plan.weather_summary or raw.get("weather_summary"),
        "day_plans": [_summarise_day(d) for d in (plan.day_plans_rich or [])[:_MAX_DAYS_SUMMARISED]],
        "rewear_strategy": [
            {
                "item_name": r.get("item_name"),
                # Rewear entries store the day labels (worn_on_days) and the
                # activities they cover (worn_for) — not a bare count/day key.
                "worn_on_days": r.get("worn_on_days") or [],
                "times": len(r.get("worn_on_days") or []),
                "worn_for": r.get("worn_for") or [],
            }
            for r in (plan.rewear_strategy or [])[:10]
        ],
        "missing_items": [
            {"name": m.get("name"), "category": m.get("category"), "reason": m.get("reason")}
            for m in (raw.get("missing_items") or raw.get("you_might_still_need") or [])[:10]
        ],
        "bag_capacity_summary": plan.bag_capacity_summary or {},
    }


async def _check_trip_weather(session: AsyncSession, _user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Fresh weather for the trip window — for "will I be warm enough" questions."""
    destination = str(args.get("destination") or "").strip()
    start = str(args.get("start_date") or "").strip()
    end = str(args.get("end_date") or "").strip()
    if not (destination and start and end):
        return {"error": "destination, start_date and end_date are required"}

    try:
        days = await weather_service.fetch_weather_async(destination, start, end)
    except Exception as exc:  # noqa: BLE001 — malformed dates are model input
        logger.warning("travel_weather_lookup_failed", error=str(exc))
        return {"error": "Weather could not be retrieved for those dates."}

    summary = weather_service.summarise_weather(days)
    return {
        "destination": destination,
        "data_source": summary.get("data_source"),
        "summary": summary,
        "days": [
            {"date": d.get("date"), "high": d.get("high"), "low": d.get("low"), "condition": d.get("condition")}
            for d in days[:_MAX_DAYS_SUMMARISED]
        ],
    }


async def _find_festivals(session: AsyncSession, _user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Festivals/events at the destination during the trip (static → live web)."""
    destination = str(args.get("destination") or "").strip()
    start = str(args.get("start_date") or "").strip()
    end = str(args.get("end_date") or "").strip()
    if not (destination and start and end):
        return {"error": "destination, start_date and end_date are required"}

    try:
        result = await festival_discovery.get_trip_festivals(
            destination, date.fromisoformat(start), date.fromisoformat(end)
        )
    except ValueError:
        return {"error": "start_date and end_date must be ISO dates (YYYY-MM-DD)."}

    return {
        "destination": destination,
        "source": result.get("source"),
        "festivals": result.get("festivals") or [],
        # Live web text is attacker-influenceable; the loop fences the whole result
        # as [USER DATA], so this passes through as data the model may summarise.
        "live_discovery": (result.get("live") or {}).get("answer") if result.get("live") else None,
    }


async def _get_venue_dress_rules(session: AsyncSession, _user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Live dress code for one venue/activity at the destination."""
    activity = str(args.get("activity") or "").strip()
    destination = str(args.get("destination") or "").strip()
    trip_start = str(args.get("start_date") or "").strip()
    if not activity:
        return {"error": "activity is required"}

    try:
        start = date.fromisoformat(trip_start) if trip_start else date.today()
    except ValueError:
        start = date.today()

    rules = await venue_rules_service.get_venue_rules([{"name": activity}], destination, start)
    if not rules:
        return {"activity": activity, "rules": None, "note": "No specific dress rules found for this venue."}
    return {"activity": activity, "rules": rules}


# ── Registry ──────────────────────────────────────────────────────────────────


def trip_plan_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="get_trip_plan",
        description=(
            "Load the generated packing plan for a trip: destination, dates, purpose, per-day "
            "outfits, rewear strategy, items still needed, weather summary, and bag capacity. "
            "ALWAYS call this first — it is the authoritative plan, and everything you say must "
            "be consistent with it. If plan_status is 'not_generated', tell the user to generate "
            "their packing plan first."
        ),
        parameters={
            "type": "object",
            "properties": {"trip_id": {"type": "string", "description": "The id of the trip being discussed."}},
            "required": ["trip_id"],
            "additionalProperties": False,
        },
        handler=lambda args: _get_trip_plan(session, user_id, args),
        result_label="Trip packing plan",
    )


def trip_weather_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="check_trip_weather",
        description=(
            "Fetch the weather forecast for the trip's destination and dates. Use for questions "
            "about temperature, rain, or whether the packed clothing suits the conditions. Pass "
            "the destination and dates from get_trip_plan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
            },
            "required": ["destination", "start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=lambda args: _check_trip_weather(session, user_id, args),
        result_label="Trip weather forecast",
    )


def festivals_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="find_festivals",
        description=(
            "Find festivals, public holidays, or cultural events at the destination during the "
            "trip, including any traditional dress. Use when the user asks whether anything "
            "special is happening or what to wear for it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
            },
            "required": ["destination", "start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=lambda args: _find_festivals(session, user_id, args),
        result_label="Destination festivals",
    )


def venue_rules_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="get_venue_dress_rules",
        description=(
            "Look up the current dress code for a specific venue or activity (a restaurant, "
            "temple, club, formal event). Use when the user asks whether their clothing meets a "
            "venue's requirements."
        ),
        parameters={
            "type": "object",
            "properties": {
                "activity": {"type": "string", "description": "The venue or activity, e.g. 'rooftop dinner'."},
                "destination": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO trip start date YYYY-MM-DD."},
            },
            "required": ["activity"],
            "additionalProperties": False,
        },
        handler=lambda args: _get_venue_dress_rules(session, user_id, args),
        result_label="Venue dress rules",
    )


def build_tools(session: AsyncSession, user_id: str) -> list[AgentTool]:
    """The travel packing advisor's tool set, bound to one request.

    ``search_closet`` and ``search_fashion_knowledge`` are shared verbatim with the
    other agents; the trip-plan anchor and the three research tools are travel-specific.
    """
    return [
        trip_plan_tool(session, user_id),
        trip_weather_tool(session, user_id),
        festivals_tool(session, user_id),
        venue_rules_tool(session, user_id),
        search_closet_tool(session, user_id),
        fashion_knowledge_tool(session, user_id),
    ]
