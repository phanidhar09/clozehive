"""Deterministic rule-based packing structures used when the AI is unavailable."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.services.packing_constants import _PURPOSE_CATEGORIES, _normalise_category

def _rule_based_packing_sections(
    closet_items: list[dict[str, Any]],
    purpose: str,
    trip_days: int,
    weather_summary: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in closet_items:
        by_category[_normalise_category(str(item.get("category", "")))].append(item)

    # Unrecognised or empty purpose falls back to the general-purpose category set.
    required = list(_PURPOSE_CATEGORIES.get(purpose.lower(), _PURPOSE_CATEGORIES["general"]))
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
    return take_from_closet, still_need


def _rule_based_day_plans(
    closet_items: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    start_date: str,
    trip_days: int,
    weather_days: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic day plans when AI is unavailable."""
    start = date.fromisoformat(start_date)
    weather_by_date: dict[str, dict[str, Any]] = {}
    if weather_days:
        for wd in weather_days:
            weather_by_date[wd.get("date", "")] = wd

    # Group activities by day
    activities_by_day: dict[int, list[dict]] = defaultdict(list)
    for act in activities:
        day_num = act.get("day_number") or 1
        activities_by_day[day_num].append(act)

    # Build closet item pool by category
    by_cat: dict[str, list] = defaultdict(list)
    for item in closet_items:
        by_cat[_normalise_category(item.get("category", ""))].append(item)

    def _pick_item(category: str, offset: int = 0) -> dict | None:
        pool = by_cat.get(category, [])
        return pool[offset % len(pool)] if pool else None

    plans: list[dict[str, Any]] = []
    for i in range(min(trip_days, 14)):
        day_num = i + 1
        day_date = (start + timedelta(days=i)).isoformat()
        weather = weather_by_date.get(day_date, {})
        day_activities = activities_by_day.get(day_num, [{"name": "General", "time_of_day": "full_day"}])

        outfits = []
        for j, act in enumerate(day_activities[:3]):
            top = _pick_item("tops", i + j)
            bottom = _pick_item("bottoms", i)
            shoes = _pick_item("shoes", 0)
            items = []
            if top:
                items.append({"closet_item_id": str(top.get("id", "")), "item_name": top.get("name", "Top"), "category": "tops", "source": "from_closet"})
            if bottom:
                items.append({"closet_item_id": str(bottom.get("id", "")), "item_name": bottom.get("name", "Bottom"), "category": "bottoms", "source": "from_closet"})
            if shoes:
                items.append({"closet_item_id": str(shoes.get("id", "")), "item_name": shoes.get("name", "Shoes"), "category": "shoes", "source": "from_closet"})
            if not items:
                items.append({"closet_item_id": None, "item_name": "Casual outfit", "category": "general", "source": "missing_recommended"})
            outfits.append({
                "slot": act.get("time_of_day", "morning") if j == 0 else ("afternoon" if j == 1 else "evening"),
                "activity": act.get("name", "General"),
                "outfit_name": f"Day {day_num} — {act.get('name', 'Outfit')}",
                "items": items,
                "styling_notes": "Mix and match with your closet items.",
                "comfort_notes": "",
                "rewear_notes": "",
            })

        plans.append({
            "day_number": day_num,
            "date": day_date,
            "weather_note": _weather_outfit_note(weather) if weather else "",
            "activities": [a.get("name", "General") for a in day_activities],
            "outfits": outfits,
        })
    return plans


def _weather_outfit_note(weather_day: dict[str, Any]) -> str:
    condition = (weather_day.get("condition") or "").lower()
    high = weather_day.get("temp_high", 20)
    if "rain" in condition or "shower" in condition or "drizzle" in condition:
        return "Rainy — wear waterproof outer layer and footwear."
    if "snow" in condition or "freez" in condition:
        return "Snowy/freezing — insulated coat, thermals, waterproof boots."
    if high >= 30:
        return f"Hot ({high}°C) — light breathable fabrics, sun hat, sunscreen."
    if high <= 10:
        return f"Cold ({high}°C) — layer up: thermal base + warm mid-layer + coat."
    if "wind" in condition:
        return "Windy — windbreaker or fitted jacket adds comfort."
    return f"Mild ({high}°C) — versatile layers work well."


def _minimal_packing_fallback(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None,
) -> dict[str, Any]:
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
        items_out = [{"name": "Travel essentials", "category": "essentials", "quantity": 1, "reason": "Add wardrobe items", "available_in_closet": False}]

    take_from_closet = [
        {"item_id": item.get("id"), "name": item.get("name") or "Wardrobe item",
         "category": item.get("category") or "general", "reason": "From your wardrobe.", "recommended_days": []}
        for item in closet_items[:12]
    ]

    return {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "purpose": purpose,
        "trip_style": None,
        "bag_size": None,
        "duration_days": 1,
        "activities": [],
        "weather_summary": {"dominant_condition": "Unknown", "avg_high": 20.0, "avg_low": 12.0, "rainy_days": 0},
        "packing_list": items_out,
        "items": items_out,
        "missing_items": [],
        "daily_plan": [],
        "day_plans_rich": [],
        "rewear_strategy": [],
        "missing_items_rich": [],
        "bag_capacity_summary": {},
        "packing_checklist": [],
        "alerts": [],
        "summary": f"Basic packing list for {destination} ({purpose}).",
        "notes": notes,
        "take_from_your_closet": take_from_closet,
        "you_might_still_need": [],
        "closet_hint": "Add closet items to get personalized packing recommendations." if not closet_items else None,
    }
