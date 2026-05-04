"""Consolidated packing service formerly provided by packing MCP."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.core.logging import get_logger
from app.services.weather_service import fetch_weather, summarise_weather

logger = get_logger("packing_service")

_PURPOSE_CATEGORIES = {
    "business": ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "leisure": ["tops", "bottoms", "shoes", "outerwear"],
    "beach": ["tops", "bottoms", "shoes", "accessories"],
    "formal": ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "adventure": ["tops", "bottoms", "shoes", "outerwear"],
}


def _normalise_category(category: str) -> str:
    category = category.lower().strip()
    if any(token in category for token in ["shirt", "top", "tee", "blouse"]):
        return "tops"
    if any(token in category for token in ["pant", "jean", "bottom", "short", "skirt"]):
        return "bottoms"
    if any(token in category for token in ["shoe", "sneaker", "boot", "sandal"]):
        return "shoes"
    return category


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
        weather_summary = summarise_weather(fetch_weather(destination, start_date, end_date))

        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in closet_items:
            by_category[_normalise_category(str(item.get("category", "")))].append(item)

        packing_list = [
            {"name": "Underwear", "category": "essentials", "quantity": trip_days, "reason": "Daily essential", "available_in_closet": False},
            {"name": "Socks", "category": "essentials", "quantity": trip_days, "reason": "Daily essential", "available_in_closet": False},
            {"name": "Phone charger", "category": "essentials", "quantity": 1, "reason": "Electronics", "available_in_closet": False},
        ]
        missing_items = []
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

        return {
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "purpose": purpose,
            "duration_days": trip_days,
            "weather_summary": weather_summary,
            "packing_list": packing_list,
            "items": packing_list,
            "missing_items": missing_items,
            "daily_plan": [],
            "alerts": [f"Missing: {', '.join({i['category'] for i in missing_items})}"] if missing_items else [],
            "summary": f"Packing list for your {purpose} trip to {destination}. Expect {weather_summary['dominant_condition'].lower()} conditions.",
            "notes": notes,
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
        {"name": item.get("name") or "Wardrobe item", "category": item.get("category") or "general", "quantity": 1,
         "reason": "From your wardrobe", "available_in_closet": True, "closet_item_id": item.get("id")}
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
    }
