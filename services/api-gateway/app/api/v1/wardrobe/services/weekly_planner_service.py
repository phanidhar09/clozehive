"""Weekly outfit planner — FANI plans a weather-aware week in ONE AI call.

Given the user's wardrobe, a per-day forecast, and the user profile, the AI
returns one outfit per day that suits the weather, avoids repeating items
across the week, and prefers least-recently-worn pieces. A deterministic
rotation fallback covers AI failures so the planner always returns a plan.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from app.api.v1.intelligence.services import ai_service, model_router
from app.api.v1.intelligence.services.model_router import Task
from app.api.v1.wardrobe.services.outfit_ai_service import _clean_json, _item_for_ai
from app.core.analytics import LLMTelemetry
from app.core.logging import get_logger

logger = get_logger("weekly_planner_service")

_RAINY_WORDS = ("rain", "shower", "drizzle", "thunder", "storm", "snow")
_COLD_HIGH_C = 15.0

_PLAN_SYSTEM_PROMPT = """\
You are FANI, ClozeHive's AI stylist. Plan one outfit for EACH day provided, \
using ONLY items from the user's wardrobe (exact ids).

RULES:
1. Every outfit must suit that day's weather (condition + temperatures). Add \
outerwear on cold (high below 15°C) or rainy days; favour breathable pieces on hot days.
2. Do NOT repeat an item on two days of the plan unless the wardrobe is too \
small to avoid it. Prefer items with low wear_count and items not worn recently.
3. Respect each day's requested occasion; if none is given, use business casual \
on weekdays and casual on weekends.
4. Each outfit needs at least a top + bottom (or a dress) and shoes when those \
categories exist in the wardrobe.
5. reasoning is 1–2 sentences a stylist would say, mentioning the weather.
6. Return ONLY valid JSON — no markdown fences.

EXACT RESPONSE SCHEMA:
{
  "days": [
    {
      "date": "YYYY-MM-DD",
      "occasion": "casual",
      "item_ids": ["uuid", "uuid"],
      "reasoning": "Why this works for the day and its weather."
    }
  ]
}"""


def infer_occasion(day: date) -> str:
    return "casual" if day.weekday() >= 5 else "business casual"


def _is_rainy(condition: str) -> bool:
    c = (condition or "").lower()
    return any(w in c for w in _RAINY_WORDS)


def _needs_outerwear(day: dict[str, Any]) -> bool:
    try:
        high = float(day.get("temp_high") or 99)
    except (TypeError, ValueError):
        high = 99
    return high < _COLD_HIGH_C or _is_rainy(str(day.get("condition") or ""))


def fallback_week_plan(
    closet_items: list[dict[str, Any]],
    days: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministic rotation when the AI is unavailable: least-worn first,
    no repeats until a category pool is exhausted, outerwear on cold/wet days."""
    pools: dict[str, list[dict[str, Any]]] = {"top": [], "bottom": [], "shoes": [], "outerwear": []}
    for item in sorted(closet_items, key=lambda i: i.get("wear_count") or 0):
        cat = (item.get("category") or "").lower()
        if cat in ("tops", "dresses"):
            pools["top"].append(item)
        elif cat == "bottoms":
            pools["bottom"].append(item)
        elif cat == "shoes":
            pools["shoes"].append(item)
        elif cat == "outerwear":
            pools["outerwear"].append(item)

    cursors = dict.fromkeys(pools, 0)

    def _next(slot: str) -> dict[str, Any] | None:
        pool = pools[slot]
        if not pool:
            return None
        item = pool[cursors[slot] % len(pool)]
        cursors[slot] += 1
        return item

    plan: list[dict[str, Any]] = []
    for day in days:
        picks = [_next("top")]
        # A dress covers the bottom slot; jeans/skirts only pair with tops.
        if picks[0] is None or (picks[0].get("category") or "").lower() != "dresses":
            picks.append(_next("bottom"))
        picks.append(_next("shoes"))
        if _needs_outerwear(day):
            picks.append(_next("outerwear"))
        chosen = [p for p in picks if p]
        plan.append(
            {
                "date": str(day.get("date")),
                "occasion": day.get("occasion") or infer_occasion(date.fromisoformat(str(day["date"]))),
                "item_ids": [str(p.get("id")) for p in chosen],
                "reasoning": (
                    f"Rotation pick for {day.get('condition') or 'mild'} weather — "
                    "least-worn pieces first so your whole closet gets airtime."
                ),
                "source": "fallback",
            }
        )
    return plan


def _validate_plan(
    data: Any,
    closet_items: list[dict[str, Any]],
    days: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Check the AI response covers every requested day with owned item ids.
    Returns the normalised per-day list, or None when unusable."""
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        return None
    valid_ids = {str(i.get("id")) for i in closet_items}
    by_date: dict[str, dict[str, Any]] = {}
    for entry in data["days"]:
        if not isinstance(entry, dict):
            continue
        ids = [str(i) for i in (entry.get("item_ids") or []) if str(i) in valid_ids]
        if not ids:
            continue
        by_date[str(entry.get("date"))] = {
            "date": str(entry.get("date")),
            "occasion": str(entry.get("occasion") or ""),
            "item_ids": ids,
            "reasoning": str(entry.get("reasoning") or ""),
            "source": "fani",
        }

    fallback_by_date = {p["date"]: p for p in fallback_week_plan(closet_items, days)}
    plan: list[dict[str, Any]] = []
    matched = 0
    for day in days:
        key = str(day.get("date"))
        if key in by_date:
            entry = by_date[key]
            if not entry["occasion"]:
                entry["occasion"] = day.get("occasion") or infer_occasion(date.fromisoformat(key))
            plan.append(entry)
            matched += 1
        elif key in fallback_by_date:
            plan.append(fallback_by_date[key])
    return plan if matched else None


async def generate_week_plan(
    closet_items: list[dict[str, Any]],
    days: list[dict[str, Any]],
    user_profile: dict[str, Any] | None = None,
    recently_worn_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Plan one outfit per forecast day. ``days`` entries carry date, condition,
    temp_high, temp_low and optionally a requested occasion."""
    if not closet_items or not days:
        return fallback_week_plan(closet_items, days)

    payload = json.dumps(
        {
            "mode": "weekly_plan",
            "days": [
                {
                    "date": str(d.get("date")),
                    "condition": d.get("condition") or "mild",
                    "temp_high_celsius": d.get("temp_high"),
                    "temp_low_celsius": d.get("temp_low"),
                    "occasion": d.get("occasion") or infer_occasion(date.fromisoformat(str(d["date"]))),
                }
                for d in days
            ],
            "recently_worn_items": recently_worn_names or [],
            "user_profile": user_profile or {},
            "wardrobe": [_item_for_ai(i) for i in closet_items],
        },
        default=str,
    )

    try:
        decision = model_router.for_task(Task.PLANNER_WEEKLY)
        raw = await ai_service.chat(
            [{"role": "user", "content": payload}],
            _PLAN_SYSTEM_PROMPT,
            model=decision.model,
            max_tokens=decision.max_tokens,
            temperature=decision.temperature,
            telemetry=LLMTelemetry(
                operation=Task.PLANNER_WEEKLY.value,
                tier=decision.tier.value,
                route_reasons=decision.reasons,
            ),
        )
        plan = _validate_plan(json.loads(_clean_json(raw)), closet_items, days)
        if plan:
            return plan
        logger.warning("weekly_plan_invalid_ai_output", days=len(days))
    except json.JSONDecodeError:
        logger.warning("weekly_plan_bad_json", days=len(days))
    except Exception as exc:
        logger.warning("weekly_plan_ai_failed", error=str(exc), days=len(days))

    return fallback_week_plan(closet_items, days)


def default_week_dates(start: date) -> list[date]:
    return [start + timedelta(days=i) for i in range(7)]
