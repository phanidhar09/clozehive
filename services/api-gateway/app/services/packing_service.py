"""Consolidated packing service — rule-based + optional AI personalisation."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.weather_service import fetch_weather_async, summarise_weather

logger = get_logger("packing_service")

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_PURPOSE_CATEGORIES: dict[str, list[str]] = {
    "business":  ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "leisure":   ["tops", "bottoms", "shoes", "outerwear"],
    "beach":     ["tops", "bottoms", "shoes", "accessories"],
    "formal":    ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "adventure": ["tops", "bottoms", "shoes", "outerwear"],
}

# Aliases used for category normalisation (also shared with rule-based matching)
_CATEGORY_ALIASES: dict[str, list[str]] = {
    "tops":        ["shirt", "top", "tee", "blouse", "sweater", "hoodie", "knitwear"],
    "bottoms":     ["pant", "jean", "bottom", "short", "skirt", "trouser", "chino"],
    "shoes":       ["shoe", "sneaker", "boot", "sandal", "loafer", "heel", "trainer"],
    "outerwear":   ["jacket", "coat", "blazer", "cardigan", "trench", "parka"],
    "dresses":     ["dress", "jumpsuit", "romper"],
    "accessories": ["bag", "hat", "scarf", "belt", "watch", "jewellery", "sunglasses"],
}


def _normalise_category(category: str) -> str:
    cat = category.lower().strip()
    for canonical, aliases in _CATEGORY_ALIASES.items():
        if cat == canonical or any(a in cat for a in aliases):
            return canonical
    return cat


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _format_closet_for_prompt(closet_items: list[dict[str, Any]]) -> str:
    """Compact JSON representation of the user's closet for the AI prompt."""
    formatted = []
    for item in closet_items:
        entry: dict[str, Any] = {"id": item.get("id"), "name": item.get("name")}
        for field in ("category", "color", "brand", "fabric", "season", "size", "notes"):
            val = item.get(field)
            if val:
                entry[field] = val
        occasions = item.get("occasion") or item.get("occasions")
        if occasions:
            entry["occasions"] = occasions
        formatted.append(entry)
    return json.dumps(formatted, ensure_ascii=False)


# ── AI recommendation call ────────────────────────────────────────────────────

async def _ai_packing_recommendations(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    trip_days: int,
    closet_items: list[dict[str, Any]],
    weather_summary: dict[str, Any],
    notes: str | None,
) -> dict[str, Any] | None:
    """
    Ask the LLM which wardrobe items to pack and what else is needed.
    Returns parsed dict or None when AI is unavailable.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    weather_text = (
        f"{weather_summary.get('dominant_condition', 'Unknown')}, "
        f"avg high {weather_summary.get('avg_high', 20):.0f}°C / "
        f"low {weather_summary.get('avg_low', 10):.0f}°C, "
        f"{weather_summary.get('rainy_days', 0)} rainy day(s)"
    )
    closet_text = _format_closet_for_prompt(closet_items) if closet_items else "[]"

    prompt = (
        "You are a professional travel stylist. Help pack for this trip.\n\n"
        "Trip details:\n"
        f"- Destination: {destination}\n"
        f"- Dates: {start_date} to {end_date} ({trip_days} days)\n"
        f"- Purpose: {purpose}\n"
        f"- Weather: {weather_text}\n"
        f"- Notes: {notes or 'None'}\n\n"
        f"User's wardrobe:\n{closet_text}\n\n"
        "From the user's wardrobe, which of these items would you recommend for this trip?\n\n"
        "Return ONLY valid JSON with this exact structure:\n"
        '{"take_from_your_closet": [{"item_id": "<id from wardrobe>", "name": "<exact name>", '
        '"category": "<category>", "reason": "<why it suits this trip>", '
        '"recommended_days": ["Day 1", "Day 2"]}], '
        '"you_might_still_need": [{"name": "<item>", "category": "<category>", '
        '"reason": "<why needed>"}]}\n\n'
        "Rules:\n"
        "- Only include items from the provided wardrobe in take_from_your_closet.\n"
        "- Do not invent wardrobe items not listed above.\n"
        "- For you_might_still_need: list items the user does NOT own but would help.\n"
        "- Prefer versatile items reusable across multiple days.\n"
        "- Consider weather, destination, purpose, and trip duration.\n"
        "- Keep recommendations practical and specific."
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _OPENAI_URL,
                json={
                    "model": _OPENAI_MODEL,
                    "max_tokens": 2000,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content) if isinstance(content, str) else content
    except Exception as exc:
        logger.warning("ai_packing_error", error=str(exc))
        return None


# ── Output normalisation ──────────────────────────────────────────────────────

def _normalise_packing_output(
    ai_data: dict[str, Any],
    closet_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Normalise AI output into (take_from_your_closet, you_might_still_need).

    - Accepts common key aliases produced by different LLM phrasings.
    - Validates every take_from_your_closet entry against the real closet (by id or name).
    - Moves hallucinated entries into you_might_still_need instead of discarding them.
    - Deduplicates both lists.
    """
    _CLOSET_KEYS = [
        "take_from_your_closet", "takeFromCloset", "take_from_closet",
        "closet_items_to_pack", "from_closet", "wardrobe_items",
    ]
    _NEED_KEYS = [
        "you_might_still_need", "youMightStillNeed", "still_need",
        "missing_items", "items_to_buy", "shopping_list",
    ]

    raw_closet: list[dict] = next(
        (ai_data[k] for k in _CLOSET_KEYS if isinstance(ai_data.get(k), list)), []
    )
    raw_need: list[dict] = next(
        (ai_data[k] for k in _NEED_KEYS if isinstance(ai_data.get(k), list)), []
    )

    valid_ids = {str(item["id"]) for item in closet_items if item.get("id")}
    valid_names_lower = {str(item.get("name", "")).lower() for item in closet_items if item.get("name")}

    take_from_closet: list[dict[str, Any]] = []
    hallucinated: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in raw_closet:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        item_id = str(entry.get("item_id") or entry.get("closet_item_id") or "")
        is_real = item_id in valid_ids or name.lower() in valid_names_lower
        normalised = {
            "item_id": item_id or None,
            "name": name,
            "category": str(entry.get("category") or "").lower() or "general",
            "reason": str(entry.get("reason") or "Recommended for this trip."),
            "recommended_days": entry.get("recommended_days") or [],
        }
        if is_real:
            take_from_closet.append(normalised)
        else:
            hallucinated.append({
                "name": name,
                "category": normalised["category"],
                "reason": normalised["reason"],
            })
        seen.add(name.lower())

    still_need: list[dict[str, Any]] = []
    seen_need: set[str] = set()
    for entry in raw_need + hallucinated:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name or name.lower() in seen_need:
            continue
        still_need.append({
            "name": name,
            "category": str(entry.get("category") or "").lower() or "general",
            "reason": str(entry.get("reason") or "Consider bringing this."),
        })
        seen_need.add(name.lower())

    return take_from_closet, still_need


# ── Rule-based fallback for new sections ─────────────────────────────────────

def _rule_based_packing_sections(
    closet_items: list[dict[str, Any]],
    purpose: str,
    trip_days: int,
    weather_summary: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic split when AI is unavailable."""
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in closet_items:
        by_category[_normalise_category(str(item.get("category", "")))].append(item)

    required = list(_PURPOSE_CATEGORIES.get(purpose.lower(), ["tops", "bottoms", "shoes"]))
    if weather_summary.get("avg_high", 20) < 10 and "outerwear" not in required:
        required.append("outerwear")

    take_from_closet: list[dict[str, Any]] = []
    still_need: list[dict[str, Any]] = []

    for category in required:
        available = by_category.get(category, [])
        needed = max(1, min(trip_days // 2, 4))
        if available:
            for item in available[:needed]:
                take_from_closet.append({
                    "item_id": item.get("id"),
                    "name": item.get("name", category.title()),
                    "category": category,
                    "reason": f"Suitable for a {purpose} trip.",
                    "recommended_days": [],
                })
        else:
            still_need.append({
                "name": f"{category.title()} (not in wardrobe)",
                "category": category,
                "reason": f"You have no {category} in your closet — consider purchasing.",
            })

    if weather_summary.get("rainy_days", 0) >= 1:
        still_need.append({
            "name": "Compact umbrella",
            "category": "accessories",
            "reason": "Rain is expected during the trip.",
        })
    if weather_summary.get("avg_high", 20) >= 28 or purpose == "beach":
        still_need.append({
            "name": "Sunscreen SPF 50+",
            "category": "essentials",
            "reason": "Sun protection for warm/beach conditions.",
        })

    return take_from_closet, still_need


# ── Daily outfit plan builder ─────────────────────────────────────────────────

def _build_daily_plan(
    take_from_closet: list[dict[str, Any]],
    start_date: str,
    trip_days: int,
    weather_days: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Build a per-day outfit plan by grouping take_from_closet items by recommended_days.
    Includes per-day weather data when provided.
    Only produces an entry for a day when at least one item is assigned to it.
    Caps at 14 days to avoid enormous lists.
    """
    start = date.fromisoformat(start_date)
    day_map: dict[str, list[dict[str, Any]]] = {}

    for item in take_from_closet:
        for label in (item.get("recommended_days") or []):
            day_map.setdefault(label, []).append(item)

    weather_by_date: dict[str, dict[str, Any]] = {}
    if weather_days:
        for wd in weather_days:
            weather_by_date[wd["date"]] = wd

    plan: list[dict[str, Any]] = []
    for i in range(min(trip_days, 14)):
        label = f"Day {i + 1}"
        items_for_day = day_map.get(label, [])
        if not items_for_day:
            continue
        day_date = (start + timedelta(days=i)).isoformat()
        entry: dict[str, Any] = {
            "date": day_date,
            "day_label": label,
            "outfit_name": f"{label} outfit",
            "items": [it["name"] for it in items_for_day],
            "item_ids": [it["item_id"] for it in items_for_day if it.get("item_id")],
        }
        if day_date in weather_by_date:
            entry["weather"] = weather_by_date[day_date]
        plan.append(entry)

    return plan


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None = None,
) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        trip_days = max(1, (end - start).days + 1)
        weather_days = await fetch_weather_async(destination, start_date, end_date)
        weather_summary = summarise_weather(weather_days)

        # ── Backward-compatible packing_list (rule-based) ─────────────────────
        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in closet_items:
            by_category[_normalise_category(str(item.get("category", "")))].append(item)

        packing_list: list[dict[str, Any]] = [
            {"name": "Underwear",     "category": "essentials", "quantity": trip_days, "reason": "Daily essential", "available_in_closet": False},
            {"name": "Socks",         "category": "essentials", "quantity": trip_days, "reason": "Daily essential", "available_in_closet": False},
            {"name": "Phone charger", "category": "essentials", "quantity": 1,         "reason": "Electronics",     "available_in_closet": False},
        ]
        missing_items: list[dict[str, Any]] = []

        for category in _PURPOSE_CATEGORIES.get(purpose.lower(), ["tops", "bottoms", "shoes"]):
            available = by_category.get(category, [])
            if available:
                for item in available[: max(1, min(trip_days // 2, 4))]:
                    packing_list.append({
                        "name": item.get("name", category.title()),
                        "category": category,
                        "quantity": 1,
                        "reason": "From your wardrobe",
                        "available_in_closet": True,
                        "closet_item_id": item.get("id"),
                    })
            else:
                missing_items.append({
                    "name": f"{category.title()} (not in wardrobe)",
                    "category": category,
                    "quantity": 1,
                    "reason": f"No {category} found in your closet",
                    "available_in_closet": False,
                })

        if weather_summary["rainy_days"]:
            packing_list.append({"name": "Compact umbrella", "category": "accessories", "quantity": 1, "reason": "Rain protection", "available_in_closet": False})
        if weather_summary["avg_high"] >= 28 or purpose == "beach":
            packing_list.append({"name": "Sunscreen SPF 50+", "category": "essentials", "quantity": 1, "reason": "Sun protection", "available_in_closet": False})

        # ── New personalised sections ─────────────────────────────────────────
        ai_data = await _ai_packing_recommendations(
            destination, start_date, end_date, purpose, trip_days,
            closet_items, weather_summary, notes,
        )

        if ai_data:
            take_from_closet, still_need = _normalise_packing_output(ai_data, closet_items)
        else:
            take_from_closet, still_need = _rule_based_packing_sections(
                closet_items, purpose, trip_days, weather_summary,
            )

        daily_plan = _build_daily_plan(take_from_closet, start_date, trip_days, weather_days)

        return {
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "purpose": purpose,
            "duration_days": trip_days,
            "weather_summary": weather_summary,
            # ── Existing fields (backward-compatible) ─────────────────────────
            "packing_list": packing_list,
            "items": packing_list,
            "missing_items": missing_items,
            "daily_plan": daily_plan,
            "alerts": [f"Missing: {', '.join({i['category'] for i in missing_items})}"] if missing_items else [],
            "summary": (
                f"Packing list for your {purpose} trip to {destination}. "
                f"Expect {weather_summary['dominant_condition'].lower()} conditions."
            ),
            "notes": notes,
            # ── New personalised fields ───────────────────────────────────────
            "take_from_your_closet": take_from_closet,
            "you_might_still_need": still_need,
            "closet_hint": "Add closet items to get personalized packing recommendations." if not closet_items else None,
        }
    except Exception as exc:
        logger.warning("packing_generation_fallback", error=str(exc), destination=destination)
        return _minimal_packing_fallback(destination, start_date, end_date, purpose, closet_items, notes)


def _minimal_packing_fallback(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None,
) -> dict[str, Any]:
    """Rule-based list when weather/date parsing fails."""
    items_out = [
        {
            "name": item.get("name") or "Wardrobe item",
            "category": item.get("category") or "general",
            "quantity": 1,
            "reason": "From your wardrobe",
            "available_in_closet": True,
            "closet_item_id": item.get("id"),
        }
        for item in closet_items[:12]
    ]
    if not items_out:
        items_out = [{
            "name": "Travel essentials",
            "category": "essentials",
            "quantity": 1,
            "reason": "Add wardrobe items or shop before departure",
            "available_in_closet": False,
        }]

    take_from_closet: list[dict[str, Any]] = [
        {
            "item_id": item.get("id"),
            "name": item.get("name") or "Wardrobe item",
            "category": item.get("category") or "general",
            "reason": "From your wardrobe.",
            "recommended_days": [],
        }
        for item in closet_items[:12]
    ]

    return {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "purpose": purpose,
        "duration_days": 1,
        "weather_summary": {"dominant_condition": "Unknown", "avg_high": 20.0, "avg_low": 12.0, "rainy_days": 0},
        "packing_list": items_out,
        "items": items_out,
        "missing_items": [],
        "daily_plan": [],
        "alerts": [],
        "summary": f"Basic packing list for {destination} ({purpose}).",
        "notes": notes,
        "take_from_your_closet": take_from_closet,
        "you_might_still_need": [],
        "closet_hint": "Add closet items to get personalized packing recommendations." if not closet_items else None,
    }
