"""Post-processing of packing AI output: normalisation, enrichment, checklist, alerts."""

from __future__ import annotations

from typing import Any

from app.services.packing_constants import _normalise_category

def _normalise_packing_output(
    ai_data: dict[str, Any],
    closet_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
            hallucinated.append({"name": name, "category": normalised["category"], "reason": normalised["reason"]})
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


# ── Enrich day_plans with closet images ──────────────────────────────────────

def _enrich_day_plans_with_images(
    day_plans: list[dict[str, Any]],
    closet_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Inject image_url into outfit items where the closet_item_id matches."""
    image_map: dict[str, str] = {
        str(item["id"]): item.get("image_url", "")
        for item in closet_items
        if item.get("id") and item.get("image_url")
    }
    for day in day_plans:
        for outfit in day.get("outfits", []):
            for item in outfit.get("items", []):
                cid = str(item.get("closet_item_id") or "")
                if cid and cid in image_map:
                    item["image_url"] = image_map[cid]
    return day_plans


# ── Packing checklist builder ─────────────────────────────────────────────────

def _build_packing_checklist(
    day_plans: list[dict[str, Any]],
    missing_items: list[dict[str, Any]],
    trip_days: int,
) -> list[dict[str, Any]]:
    """
    Aggregate all outfit items across day plans into a grouped packing checklist.
    Deduplicated by closet_item_id (preferred) or item_name.
    """
    checklist: dict[str, dict[str, Any]] = {}

    for day in day_plans:
        day_label = f"Day {day.get('day_number', '?')}"
        for outfit in day.get("outfits", []):
            activity = outfit.get("activity", "")
            for item in outfit.get("items", []):
                cid = str(item.get("closet_item_id") or "")
                name = str(item.get("item_name") or item.get("name") or "")
                if not name:
                    continue
                key = cid if cid else name.lower()
                if key not in checklist:
                    checklist[key] = {
                        "item_name": name,
                        "category": _normalise_category(item.get("category") or "general"),
                        "closet_item_id": cid or None,
                        "image_url": item.get("image_url"),
                        "source": item.get("source", "from_closet"),
                        "quantity": 1,
                        "planned_days": [],
                        "activities": [],
                        "rewear_count": 0,
                        "is_packed": False,
                    }
                entry = checklist[key]
                if day_label not in entry["planned_days"]:
                    entry["planned_days"].append(day_label)
                    entry["rewear_count"] = len(entry["planned_days"])
                if activity and activity not in entry["activities"]:
                    entry["activities"].append(activity)

    # Add missing items to checklist (labelled separately)
    for mi in missing_items:
        name = mi.get("item_name") or mi.get("name") or ""
        if not name:
            continue
        key = f"missing_{name.lower()}"
        if key not in checklist:
            checklist[key] = {
                "item_name": name,
                "category": _normalise_category(mi.get("category") or "general"),
                "closet_item_id": None,
                "image_url": None,
                "source": "missing_recommended",
                "quantity": 1,
                "planned_days": [],
                "activities": [mi.get("needed_for", "")] if mi.get("needed_for") else [],
                "rewear_count": 0,
                "is_packed": False,
                "priority": mi.get("priority", "recommended"),
                "reason": mi.get("reason", ""),
            }

    # Add standard essentials
    essentials = [
        {"item_name": "Underwear", "category": "innerwear", "quantity": trip_days, "source": "essential"},
        {"item_name": "Socks", "category": "innerwear", "quantity": trip_days, "source": "essential"},
        {"item_name": "Sleepwear", "category": "sleepwear", "quantity": 1, "source": "essential"},
        {"item_name": "Phone charger", "category": "travel_essentials", "quantity": 1, "source": "essential"},
        {"item_name": "Toiletries bag", "category": "toiletries", "quantity": 1, "source": "essential"},
        {"item_name": "Medications (if needed)", "category": "travel_essentials", "quantity": 1, "source": "optional"},
    ]
    for e in essentials:
        key = f"essential_{e['item_name'].lower()}"
        if key not in checklist:
            checklist[key] = {
                **e,
                "closet_item_id": None,
                "image_url": None,
                "planned_days": [],
                "activities": [],
                "rewear_count": 0,
                "is_packed": False,
            }

    return list(checklist.values())


def _weather_alerts(weather_summary: dict[str, Any], trip_days: int) -> list[str]:
    alerts: list[str] = []
    avg_high = weather_summary.get("avg_high", 20)
    avg_low = weather_summary.get("avg_low", 10)
    rainy_days = weather_summary.get("rainy_days", 0)
    dominant = (weather_summary.get("dominant_condition") or "").lower()
    if rainy_days >= trip_days // 2:
        alerts.append(f"Rain expected on {rainy_days}/{trip_days} days — waterproof layers essential.")
    elif rainy_days >= 1:
        alerts.append(f"Rain expected on {rainy_days} day(s) — pack umbrella and light waterproof layer.")
    if avg_high >= 35:
        alerts.append(f"Extreme heat ({avg_high:.0f}°C) — breathable fabrics and sun protection essential.")
    elif avg_high >= 28:
        alerts.append(f"Warm weather ({avg_high:.0f}°C) — light clothing and sun protection recommended.")
    if avg_low < 0:
        alerts.append(f"Sub-zero nights ({avg_low:.0f}°C) — thermals and insulated footwear a must.")
    elif avg_high <= 12:
        alerts.append(f"Cold (avg high {avg_high:.0f}°C) — warm layers and outerwear needed.")
    if "snow" in dominant:
        alerts.append("Snow forecast — waterproof boots and heavy insulation recommended.")
    return alerts


# ── Build legacy daily_plan from rich day_plans ──────────────────────────────

def _build_legacy_daily_plan(
    day_plans_rich: list[dict[str, Any]],
    closet_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert rich day_plans to legacy daily_plan format for backward compat."""
    plan = []
    for day in day_plans_rich:
        all_items: list[str] = []
        all_ids: list[str] = []
        outfit_names: list[str] = []
        for outfit in day.get("outfits", []):
            outfit_names.append(outfit.get("outfit_name", ""))
            for item in outfit.get("items", []):
                name = item.get("item_name", "")
                cid = str(item.get("closet_item_id") or "")
                if name and name not in all_items:
                    all_items.append(name)
                if cid and cid not in all_ids:
                    all_ids.append(cid)
        plan.append({
            "date": day.get("date", ""),
            "day_label": f"Day {day.get('day_number', '?')}",
            "outfit_name": " + ".join(filter(None, outfit_names[:2])) or f"Day {day.get('day_number')} outfit",
            "items": all_items,
            "item_ids": all_ids,
            "activities": day.get("activities", []),
            "weather_note": day.get("weather_note", ""),
        })
    return plan

