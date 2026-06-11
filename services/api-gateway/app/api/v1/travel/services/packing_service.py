"""
Activity-aware travel packing service.

Generates a day-by-day outfit planner driven by planned activities,
bag size constraints, weather, user style profile, and real closet items.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from langsmith import traceable
from openai import AsyncOpenAI

from app.api.v1.intelligence.services import festival_discovery
from app.api.v1.travel.services import venue_rules_service
from app.api.v1.travel.services.location_intel_service import (
    build_location_context_block_async,
)
from app.api.v1.travel.services.weather_service import fetch_weather_async, summarise_weather
from app.core.config import get_settings
from app.core.constraint_priority import build_constraint_priority_block
from app.core.llm_safety import sanitize_user_text
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client

logger = get_logger("packing_service")
settings = get_settings()

_packing_llm: AsyncOpenAI | None = None


def _packing_openai_client() -> AsyncOpenAI | None:
    global _packing_llm
    if not settings.openai_api_key:
        return None
    if _packing_llm is None:
        _packing_llm = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url),
        )
    return _packing_llm


def _packing_chat_model() -> str:
    return settings.openai_model


# ── Category aliases ──────────────────────────────────────────────────────────

_CATEGORY_ALIASES: dict[str, list[str]] = {
    "tops": ["shirt", "top", "tee", "blouse", "sweater", "hoodie", "knitwear", "polo"],
    "bottoms": ["pant", "jean", "bottom", "short", "skirt", "trouser", "chino", "legging"],
    "shoes": ["shoe", "sneaker", "boot", "sandal", "loafer", "heel", "trainer", "mule", "slipper"],
    "outerwear": ["jacket", "coat", "blazer", "cardigan", "trench", "parka", "vest", "overshirt"],
    "dresses": ["dress", "jumpsuit", "romper", "co-ord"],
    "accessories": ["bag", "hat", "scarf", "belt", "watch", "jewellery", "sunglasses", "cap", "tote"],
    "innerwear": ["underwear", "bra", "brief", "boxers", "socks", "lingerie"],
}

_PURPOSE_CATEGORIES: dict[str, list[str]] = {
    "business": ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "leisure": ["tops", "bottoms", "shoes", "outerwear"],
    "beach": ["tops", "bottoms", "shoes", "accessories"],
    "formal": ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "adventure": ["tops", "bottoms", "shoes", "outerwear"],
    # Default when no activity/purpose is given — versatile everyday coverage.
    "general": ["tops", "bottoms", "shoes", "outerwear", "accessories"],
}

# ── Bag size constraints ──────────────────────────────────────────────────────

BAG_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "backpack": {
        "max_tops": 3,
        "max_bottoms": 2,
        "max_shoes": 1,
        "max_outerwear": 1,
        "max_accessories": 2,
        "rewear_days": 2,
        "label": "Backpack only",
        "hint": (
            "VERY LIMITED SPACE. Max 2-3 tops, 1-2 bottoms, 1 pair shoes. "
            "Strong rewear strategy essential. Prioritize multi-purpose items only. "
            "Avoid bulky items. Every item must serve 2+ purposes."
        ),
    },
    "carry_on": {
        "max_tops": 5,
        "max_bottoms": 3,
        "max_shoes": 2,
        "max_outerwear": 1,
        "max_accessories": 3,
        "rewear_days": 2,
        "label": "Carry-on suitcase",
        "hint": (
            "Moderate space. Max 4-5 tops, 2-3 bottoms, 1-2 shoes, 1 outerwear piece. "
            "Key items should rewear across 2 days. Pack versatile neutrals."
        ),
    },
    "medium_suitcase": {
        "max_tops": 8,
        "max_bottoms": 4,
        "max_shoes": 3,
        "max_outerwear": 2,
        "max_accessories": 4,
        "rewear_days": 2,
        "label": "Medium suitcase",
        "hint": (
            "Good space. Up to 6-8 tops, 3-4 bottoms, 2-3 shoes. "
            "Some variety allowed. Still suggest rewearing key pieces."
        ),
    },
    "large_suitcase": {
        "max_tops": 12,
        "max_bottoms": 6,
        "max_shoes": 4,
        "max_outerwear": 3,
        "max_accessories": 6,
        "rewear_days": 1,
        "label": "Large suitcase",
        "hint": (
            "Plenty of space. Full outfit variety possible. "
            "Avoid unnecessary duplication but comfort and coverage is priority."
        ),
    },
    "none": {
        "max_tops": 8,
        "max_bottoms": 4,
        "max_shoes": 3,
        "max_outerwear": 2,
        "max_accessories": 4,
        "rewear_days": 2,
        "label": "Not specified",
        "hint": "Pack sensibly for the trip length. Suggest rewearing versatile items.",
    },
}


def _get_bag_constraints(bag_size: str | None) -> dict[str, Any]:
    return BAG_CONSTRAINTS.get(bag_size or "none", BAG_CONSTRAINTS["none"])


# ── Formatters ────────────────────────────────────────────────────────────────


def _normalise_category(category: str) -> str:
    cat = category.lower().strip()
    for canonical, aliases in _CATEGORY_ALIASES.items():
        if cat == canonical or any(a in cat for a in aliases):
            return canonical
    return cat


def _format_closet_for_prompt(closet_items: list[dict[str, Any]]) -> str:
    formatted = []
    for item in closet_items:
        entry: dict[str, Any] = {
            "id": item.get("id"),
            "name": item.get("name"),
            "category": item.get("category"),
        }
        for field in ("color", "brand", "fabric", "pattern", "season", "size", "notes"):
            val = item.get(field)
            if val:
                entry[field] = val
        occasions = item.get("occasion") or item.get("occasions")
        if occasions:
            entry["occasions"] = occasions
        formatted.append(entry)
    return json.dumps(formatted, ensure_ascii=False)


def _format_activities_for_prompt(activities: list[dict[str, Any]]) -> str:
    if not activities:
        return "No specific activities listed — use trip purpose and notes to guide outfit choices."
    lines = []
    for i, act in enumerate(activities, 1):
        # Sanitise every user-supplied field before embedding in the prompt.
        safe_name = sanitize_user_text(act.get("name", "Activity"), field="activity")
        line = f"  {i}. {safe_name}"
        if act.get("day_number"):
            line += f" — Day {act['day_number']}"
        if act.get("date"):
            line += f" ({act['date']})"
        if act.get("time_of_day"):
            line += f", {act['time_of_day'].replace('_', ' ')}"
        if act.get("formality"):
            line += f", dress code: {act['formality'].replace('_', ' ')}"
        if act.get("is_fixed"):
            line += " ⚠️ [BOOKED — must plan outfit]"
        if act.get("notes"):
            safe_notes = sanitize_user_text(act["notes"], field="activity", max_len=200)
            line += f" | Notes: {safe_notes}"
        lines.append(line)
    return "\n".join(lines)


def _per_day_weather_table(weather_days: list[dict[str, Any]]) -> str:
    if not weather_days:
        return ""
    lines = ["Per-day weather forecast:"]
    for i, wd in enumerate(weather_days[:14], 1):
        lines.append(
            f"  Day {i} ({wd.get('date', '?')}): {wd.get('condition', '?')} | "
            f"High {wd.get('temp_high', '?')}°C / Low {wd.get('temp_low', '?')}°C"
        )
    return "\n".join(lines)


# ── AI packing prompt (activity-aware) ────────────────────────────────────────


async def _ai_activity_aware_packing(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    trip_style: str | None,
    bag_size: str | None,
    trip_days: int,
    closet_items: list[dict[str, Any]],
    weather_summary: dict[str, Any],
    weather_days: list[dict[str, Any]] | None,
    activities: list[dict[str, Any]],
    notes: str | None,
    style_profile_context_text: str | None = None,
    rag_context: str | None = None,
    location_context: str | None = None,
) -> dict[str, Any] | None:
    """
    Core AI call — generates a full activity-aware day-by-day outfit planner.
    Returns parsed dict or None if AI unavailable.
    """
    client = _packing_openai_client()
    if not client:
        return None

    bag = _get_bag_constraints(bag_size)
    weather_text = (
        f"{weather_summary.get('dominant_condition', 'Unknown')}, "
        f"avg high {weather_summary.get('avg_high', 22):.0f}°C / "
        f"low {weather_summary.get('avg_low', 15):.0f}°C, "
        f"{weather_summary.get('rainy_days', 0)} rainy day(s)"
    )
    per_day_block = _per_day_weather_table(weather_days or weather_summary.get("days", []))
    activities_block = _format_activities_for_prompt(activities)
    closet_text = _format_closet_for_prompt(closet_items) if closet_items else "[]"
    style_block = ""
    if style_profile_context_text and style_profile_context_text.strip():
        style_block = (
            "\nUser style profile (on EVERY outfit, respect their preferences, body size, "
            "skin tone & undertone, and fit; choose colours that flatter their skin tone, "
            "favour flattering cuts for their build, and never use avoided colours):\n"
            f"{style_profile_context_text.strip()}\n"
        )
    if rag_context and rag_context.strip():
        style_block += f"\nFashion context:\n{rag_context.strip()}\n"
    location_block = ""
    if location_context and location_context.strip():
        location_block = f"\n{location_context.strip()}\n"

    prompt = f"""You are FANI, a professional travel stylist and personal wardrobe manager. Generate a day-by-day travel outfit planner.

TRIP DETAILS:
- Destination: {destination}
- Dates: {start_date} to {end_date} ({trip_days} days)
- Purpose: {purpose}
- Trip style: {trip_style or "not specified"}
- Bag size: {bag["label"]}
- Weather: {weather_text}
{per_day_block}
- Notes: {notes or "None"}
{location_block}{style_block}
PLANNED ACTIVITIES:
{activities_block}

BAG SIZE CONSTRAINT: {bag["hint"]}

USER'S CLOSET (ONLY use items from this list — never invent closet items):
{closet_text}

INSTRUCTIONS:
1. ACTIVITIES ARE THE #1 PRIORITY. When the user has listed planned activities,
   they OUTRANK every other signal (purpose, trip style, general weather). Build
   the plan around them first: every listed activity MUST have at least one
   purpose-appropriate outfit before you add any general/filler outfits. Match
   each outfit's formality, footwear, and fabric to what the activity demands
   (e.g. business meeting → formal shoes + blazer; hike → trail shoes + layers;
   beach → swimwear + sandals; gym → athletic wear). Only if NO activities are
   listed do you fall back to the trip purpose for guidance.
2. Fixed/booked activities MUST have an outfit planned first, before anything else.
3. Respect time of day and formality for each activity.
4. Use ONLY closet items for from_closet outfits. If item is missing, mark source as "missing_recommended".
5. If the wardrobe lacks an item an activity genuinely needs, add it to missing_items
   with needed_for set to that activity — never substitute an unsuitable item.
6. Suggest rewearing: bottoms across 2-3 days, shoes across multiple outfits, outerwear often.
7. Never suggest rewearing gym/beach/sweaty items unless specifically noted.
8. Keep total unique items within bag size limits.
9. Provide clear styling notes and rewear notes per outfit slot.
10. Activity priority order: fixed/booked > time-specific > general everyday wear.
11. LOCATION NORMS ARE CONSTRAINTS. If destination location preferences are given above,
    respect the local climate, modesty level, formality baseline, and cultural dress norms:
    prefer wardrobe items that fit them, suggest cover-ups/layers from the closet where coverage
    is needed (temples, mosques, conservative areas), and never plan items that would violate
    local norms. Summarise the single most useful local dressing tip in trip_summary.location_etiquette.

Return ONLY valid JSON with this structure:
{{
  "trip_summary": {{
    "style_direction": "2-3 sentence description of the overall style approach for this trip",
    "climate_summary": "brief climate description and what it means for dressing",
    "location_etiquette": "1-2 sentence note on local dress norms/modesty/culture for this destination and how the plan respects them"
  }},
  "day_plans": [
    {{
      "day_number": 1,
      "date": "YYYY-MM-DD",
      "weather_note": "brief weather note for the day",
      "activities": ["list of activity names for this day"],
      "outfits": [
        {{
          "slot": "morning",
          "activity": "name of activity this outfit is for",
          "outfit_name": "short descriptive name",
          "items": [
            {{
              "closet_item_id": "exact id from closet JSON above, or null if missing",
              "item_name": "exact name from closet or recommended missing item name",
              "category": "tops|bottoms|shoes|outerwear|accessories|dresses|innerwear",
              "source": "from_closet|missing_recommended|optional"
            }}
          ],
          "styling_notes": "how to style this outfit, what accessories work",
          "comfort_notes": "comfort tip for weather/activity",
          "rewear_notes": "if any item rewears from another day, note it here"
        }}
      ]
    }}
  ],
  "rewear_strategy": [
    {{
      "item_name": "item name",
      "closet_item_id": "id or null",
      "worn_on_days": ["Day 1", "Day 3"],
      "worn_for": ["Sightseeing", "Airport"],
      "reason": "why this item rewears well"
    }}
  ],
  "missing_items": [
    {{
      "item_name": "item name",
      "category": "category",
      "needed_for": "which activity/day",
      "priority": "essential|recommended|optional",
      "reason": "why needed"
    }}
  ],
  "bag_capacity_summary": {{
    "packing_status": "fits|tight|overpacked",
    "total_unique_items": 0,
    "optimization_notes": ["practical packing tip 1", "practical packing tip 2"]
  }}
}}"""

    try:
        resp = await client.chat.completions.create(
            model=_packing_chat_model(),
            max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            timeout=45.0,
        )
        content = resp.choices[0].message.content
        return json.loads(content) if isinstance(content, str) else content
    except Exception as exc:
        logger.warning("ai_activity_packing_error", error=str(exc))
        return None


# ── Legacy AI call (kept for fallback) ───────────────────────────────────────


async def _ai_packing_recommendations(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    trip_days: int,
    closet_items: list[dict[str, Any]],
    weather_summary: dict[str, Any],
    notes: str | None,
    style_profile_context_text: str | None = None,
    weather_days: list[dict[str, Any]] | None = None,
    rag_context: str | None = None,
) -> dict[str, Any] | None:
    """Legacy AI call for take_from_your_closet / you_might_still_need format."""
    client = _packing_openai_client()
    if not client:
        return None

    weather_text = (
        f"{weather_summary.get('dominant_condition', 'Unknown')}, "
        f"avg high {weather_summary.get('avg_high', 20):.0f}°C / "
        f"low {weather_summary.get('avg_low', 10):.0f}°C, "
        f"{weather_summary.get('rainy_days', 0)} rainy day(s)"
    )
    per_day_block = _per_day_weather_table(weather_days or weather_summary.get("days", []))
    closet_text = _format_closet_for_prompt(closet_items) if closet_items else "[]"
    style_block = ""
    if style_profile_context_text and style_profile_context_text.strip():
        style_block = f"\nPersonalisation:\n{style_profile_context_text.strip()}\n\n"
    if rag_context and rag_context.strip():
        style_block += f"\nRAG Context:\n{rag_context.strip()}\n\n"

    # Sanitise user-supplied trip fields before embedding in the prompt.
    safe_destination = sanitize_user_text(destination, field="notes", max_len=120)
    safe_purpose = sanitize_user_text(purpose, field="notes", max_len=80)
    safe_notes = sanitize_user_text(notes or "", field="trip_notes") or "None"

    prompt = (
        "You are a professional travel stylist. Help pack for this trip.\n\n"
        f"Trip: {safe_destination} | {start_date} to {end_date} ({trip_days} days) | {safe_purpose}\n"
        f"Weather: {weather_text}\n{per_day_block}\n"
        f"Notes: {safe_notes}\n{style_block}"
        f"Wardrobe:\n{closet_text}\n\n"
        "Return ONLY valid JSON:\n"
        '{"take_from_your_closet": [{"item_id": "<id>", "name": "<name>", "category": "<cat>", '
        '"reason": "<why>", "recommended_days": ["Day 1"]}], '
        '"you_might_still_need": [{"name": "<item>", "category": "<cat>", "reason": "<why>"}]}\n\n'
        "Rules: Only use closet items in take_from_your_closet. Never invent items."
    )
    try:
        resp = await client.chat.completions.create(
            model=_packing_chat_model(),
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        content = resp.choices[0].message.content
        return json.loads(content) if isinstance(content, str) else content
    except Exception as exc:
        logger.warning("ai_packing_error", error=str(exc))
        return None


# ── Normalisation helpers ─────────────────────────────────────────────────────


def _normalise_packing_output(
    ai_data: dict[str, Any],
    closet_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _CLOSET_KEYS = [
        "take_from_your_closet",
        "takeFromCloset",
        "take_from_closet",
        "closet_items_to_pack",
        "from_closet",
        "wardrobe_items",
    ]
    _NEED_KEYS = [
        "you_might_still_need",
        "youMightStillNeed",
        "still_need",
        "missing_items",
        "items_to_buy",
        "shopping_list",
    ]
    raw_closet: list[dict] = next((ai_data[k] for k in _CLOSET_KEYS if isinstance(ai_data.get(k), list)), [])
    raw_need: list[dict] = next((ai_data[k] for k in _NEED_KEYS if isinstance(ai_data.get(k), list)), [])
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
        still_need.append(
            {
                "name": name,
                "category": str(entry.get("category") or "").lower() or "general",
                "reason": str(entry.get("reason") or "Consider bringing this."),
            }
        )
        seen_need.add(name.lower())
    return take_from_closet, still_need


# ── Enrich day_plans with closet images ──────────────────────────────────────


def _enrich_day_plans_with_images(
    day_plans: list[dict[str, Any]],
    closet_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Inject image_url into outfit items where the closet_item_id matches."""
    image_map: dict[str, str] = {
        str(item["id"]): item.get("image_url", "") for item in closet_items if item.get("id") and item.get("image_url")
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


# ── Rule-based fallback structures ───────────────────────────────────────────


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
                take_from_closet.append(
                    {
                        "item_id": item.get("id"),
                        "name": item.get("name", category.title()),
                        "category": category,
                        "reason": f"Suitable for a {purpose} trip.",
                        "recommended_days": [],
                    }
                )
        else:
            still_need.append(
                {
                    "name": f"{category.title()} (not in wardrobe)",
                    "category": category,
                    "reason": f"You have no {category} in your closet — consider purchasing.",
                }
            )
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
                items.append(
                    {
                        "closet_item_id": str(top.get("id", "")),
                        "item_name": top.get("name", "Top"),
                        "category": "tops",
                        "source": "from_closet",
                    }
                )
            if bottom:
                items.append(
                    {
                        "closet_item_id": str(bottom.get("id", "")),
                        "item_name": bottom.get("name", "Bottom"),
                        "category": "bottoms",
                        "source": "from_closet",
                    }
                )
            if shoes:
                items.append(
                    {
                        "closet_item_id": str(shoes.get("id", "")),
                        "item_name": shoes.get("name", "Shoes"),
                        "category": "shoes",
                        "source": "from_closet",
                    }
                )
            if not items:
                items.append(
                    {
                        "closet_item_id": None,
                        "item_name": "Casual outfit",
                        "category": "general",
                        "source": "missing_recommended",
                    }
                )
            outfits.append(
                {
                    "slot": act.get("time_of_day", "morning") if j == 0 else ("afternoon" if j == 1 else "evening"),
                    "activity": act.get("name", "General"),
                    "outfit_name": f"Day {day_num} — {act.get('name', 'Outfit')}",
                    "items": items,
                    "styling_notes": "Mix and match with your closet items.",
                    "comfort_notes": "",
                    "rewear_notes": "",
                }
            )

        plans.append(
            {
                "day_number": day_num,
                "date": day_date,
                "weather_note": _weather_outfit_note(weather) if weather else "",
                "activities": [a.get("name", "General") for a in day_activities],
                "outfits": outfits,
            }
        )
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


# ── Weather alerts ───────────────────────────────────────────────────────────


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
        plan.append(
            {
                "date": day.get("date", ""),
                "day_label": f"Day {day.get('day_number', '?')}",
                "outfit_name": " + ".join(filter(None, outfit_names[:2])) or f"Day {day.get('day_number')} outfit",
                "items": all_items,
                "item_ids": all_ids,
                "activities": day.get("activities", []),
                "weather_note": day.get("weather_note", ""),
            }
        )
    return plan


# ── Public API ────────────────────────────────────────────────────────────────


@traceable(name="gateway_packing_generate_list", run_type="chain")
async def generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None = None,
    *,
    activities: list[dict[str, Any]] | None = None,
    trip_style: str | None = None,
    bag_size: str | None = None,
    style_profile_context_text: str | None = None,
    user_style_profile: dict[str, Any] | None = None,
    rag_context: str | None = None,
) -> dict[str, Any]:
    try:
        activities = activities or []
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        trip_days = max(1, (end - start).days + 1)

        weather_days = await fetch_weather_async(destination, start_date, end_date)
        weather_summary = summarise_weather(weather_days)
        if weather_summary.get("data_source") != "live":
            logger.warning(
                "packing_weather_fallback", destination=destination, data_source=weather_summary.get("data_source")
            )

        merged_ctx = style_profile_context_text
        if merged_ctx is None and user_style_profile:
            merged_ctx = user_style_profile.get("style_profile_context_text")

        # ── Destination location preferences (curated > live web > LLM fallback) ─
        location_context = await build_location_context_block_async(destination, mode="travel")

        # ── Festivals at the destination during the trip (static > live web) ──
        festival_block = ""
        try:
            fest_result = await festival_discovery.get_trip_festivals(destination, start, end)
            festival_block = festival_discovery.build_trip_festival_block(fest_result)
            if festival_block:
                location_context = f"{location_context}\n\n{festival_block}" if location_context else festival_block
        except Exception as exc:  # noqa: BLE001 — festival layer is best-effort
            logger.warning("packing_festival_failed", error=str(exc))

        # ── Venue/event dress rules for declared activities (live web) ────────
        venue_block = ""
        try:
            venue_rules = await venue_rules_service.get_venue_rules(activities, destination, start)
            venue_block = venue_rules_service.build_venue_rules_block(venue_rules)
            if venue_block:
                location_context = f"{location_context}\n\n{venue_block}" if location_context else venue_block
        except Exception as exc:  # noqa: BLE001 — venue-rules layer is best-effort
            logger.warning("packing_venue_rules_failed", error=str(exc))

        # ── Constraint priority — one arbitration preamble for the stacked layers ─
        priority_block = build_constraint_priority_block(
            mandatory=bool(venue_block) or bool(location_context),
            weather=True,  # packing is always weather-driven
            occasion=bool(festival_block),
            style=bool(merged_ctx and merged_ctx.strip()),
        )
        if priority_block:
            location_context = f"{priority_block}\n\n{location_context}" if location_context else priority_block

        # ── New activity-aware AI call ────────────────────────────────────────
        ai_rich = await _ai_activity_aware_packing(
            destination,
            start_date,
            end_date,
            purpose,
            trip_style,
            bag_size,
            trip_days,
            closet_items,
            weather_summary,
            weather_days,
            activities,
            notes,
            style_profile_context_text=merged_ctx,
            rag_context=rag_context,
            location_context=location_context,
        )

        # ── Legacy AI call for backward-compat take_from / you_might_need ────
        ai_legacy = await _ai_packing_recommendations(
            destination,
            start_date,
            end_date,
            purpose,
            trip_days,
            closet_items,
            weather_summary,
            notes,
            style_profile_context_text=merged_ctx,
            weather_days=weather_days,
            rag_context=rag_context,
        )

        # ── Process rich AI output ────────────────────────────────────────────
        day_plans_rich: list[dict[str, Any]] = []
        rewear_strategy: list[dict[str, Any]] = []
        missing_items_rich: list[dict[str, Any]] = []
        bag_capacity_summary: dict[str, Any] = {}
        trip_style_direction: str | None = None
        climate_summary: str | None = None
        location_etiquette: str | None = None

        if ai_rich:
            day_plans_rich = ai_rich.get("day_plans") or []
            rewear_strategy = ai_rich.get("rewear_strategy") or []
            missing_items_rich = ai_rich.get("missing_items") or []
            bag_capacity_summary = ai_rich.get("bag_capacity_summary") or {}
            summary_block = ai_rich.get("trip_summary") or {}
            trip_style_direction = summary_block.get("style_direction")
            climate_summary = summary_block.get("climate_summary")
            location_etiquette = summary_block.get("location_etiquette")

            # Enrich with closet images
            day_plans_rich = _enrich_day_plans_with_images(day_plans_rich, closet_items)
        else:
            # Fallback rule-based rich plans
            day_plans_rich = _rule_based_day_plans(closet_items, activities, start_date, trip_days, weather_days)

        # ── Process legacy AI output ──────────────────────────────────────────
        if ai_legacy:
            take_from_closet, still_need = _normalise_packing_output(ai_legacy, closet_items)
        else:
            take_from_closet, still_need = _rule_based_packing_sections(
                closet_items,
                purpose,
                trip_days,
                weather_summary,
            )

        # ── Build checklist ───────────────────────────────────────────────────
        packing_checklist = _build_packing_checklist(day_plans_rich, missing_items_rich, trip_days)

        # ── Legacy packing_list (rule-based, backward compat) ─────────────────
        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in closet_items:
            by_category[_normalise_category(str(item.get("category", "")))].append(item)

        packing_list: list[dict[str, Any]] = [
            {
                "name": "Underwear",
                "category": "essentials",
                "quantity": trip_days,
                "reason": "Daily essential",
                "available_in_closet": False,
            },
            {
                "name": "Socks",
                "category": "essentials",
                "quantity": trip_days,
                "reason": "Daily essential",
                "available_in_closet": False,
            },
            {
                "name": "Phone charger",
                "category": "essentials",
                "quantity": 1,
                "reason": "Electronics",
                "available_in_closet": False,
            },
        ]
        missing_legacy: list[dict[str, Any]] = []
        for category in _PURPOSE_CATEGORIES.get(purpose.lower(), ["tops", "bottoms", "shoes"]):
            available = by_category.get(category, [])
            if available:
                for item in available[: max(1, min(trip_days // 2, 4))]:
                    packing_list.append(
                        {
                            "name": item.get("name", category.title()),
                            "category": category,
                            "quantity": 1,
                            "reason": "From your wardrobe",
                            "available_in_closet": True,
                            "closet_item_id": item.get("id"),
                        }
                    )
            else:
                missing_legacy.append(
                    {
                        "name": f"{category.title()} (not in wardrobe)",
                        "category": category,
                        "quantity": 1,
                        "reason": f"No {category} found",
                        "available_in_closet": False,
                    }
                )

        avg_high = weather_summary.get("avg_high", 20)
        avg_low = weather_summary.get("avg_low", 10)
        dominant = (weather_summary.get("dominant_condition") or "").lower()
        if weather_summary.get("rainy_days"):
            packing_list.append(
                {
                    "name": "Compact umbrella",
                    "category": "accessories",
                    "quantity": 1,
                    "reason": "Rain protection",
                    "available_in_closet": False,
                }
            )
        if avg_high >= 28 or purpose == "beach":
            packing_list.append(
                {
                    "name": "Sunscreen SPF 50+",
                    "category": "essentials",
                    "quantity": 1,
                    "reason": "Sun protection",
                    "available_in_closet": False,
                }
            )
            packing_list.append(
                {
                    "name": "Sunglasses",
                    "category": "accessories",
                    "quantity": 1,
                    "reason": "Eye protection",
                    "available_in_closet": False,
                }
            )
        if avg_high <= 12 or any(w in dominant for w in ("cold", "snow", "freez")):
            packing_list.append(
                {
                    "name": "Thermal base layer",
                    "category": "essentials",
                    "quantity": 2,
                    "reason": f"Cold weather ({avg_high:.0f}°C)",
                    "available_in_closet": False,
                }
            )
        if avg_low < 0 or "snow" in dominant:
            packing_list.append(
                {
                    "name": "Heavy insulated coat",
                    "category": "outerwear",
                    "quantity": 1,
                    "reason": f"Sub-zero/snowy ({avg_low:.0f}°C)",
                    "available_in_closet": False,
                }
            )
        if purpose == "beach":
            packing_list.append(
                {
                    "name": "Swimwear",
                    "category": "essentials",
                    "quantity": 2,
                    "reason": "Beach trip essential",
                    "available_in_closet": False,
                }
            )

        # ── Build legacy daily_plan from rich plans ────────────────────────────
        daily_plan = _build_legacy_daily_plan(day_plans_rich, closet_items)

        weather_alerts = _weather_alerts(weather_summary, trip_days)
        missing_alerts = [f"Missing: {', '.join({i['category'] for i in missing_legacy})}"] if missing_legacy else []

        summary_text = (
            f"Packing plan for your {purpose} trip to {destination} ({trip_days} days). "
            + (f"Style: {trip_style.replace('_', ' ')}. " if trip_style else "")
            + (f"Bag: {_get_bag_constraints(bag_size)['label']}. " if bag_size else "")
            + f"Expect {weather_summary['dominant_condition'].lower()} conditions "
            f"(avg {weather_summary['avg_high']:.0f}°C / {weather_summary['avg_low']:.0f}°C). "
            f"{weather_summary.get('recommendation', '')}"
        )

        return {
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "purpose": purpose,
            "trip_style": trip_style,
            "bag_size": bag_size,
            "duration_days": trip_days,
            "activities": activities,
            "weather_summary": weather_summary,
            "weather_forecast": weather_days,
            # ── New rich fields ───────────────────────────────────────────────
            "day_plans_rich": day_plans_rich,
            "rewear_strategy": rewear_strategy,
            "missing_items_rich": missing_items_rich,
            "bag_capacity_summary": bag_capacity_summary,
            "packing_checklist": packing_checklist,
            "trip_style_direction": trip_style_direction,
            "climate_summary": climate_summary,
            "location_etiquette": location_etiquette,
            # ── Legacy fields (backward compat) ──────────────────────────────
            "packing_list": packing_list,
            "items": packing_list,
            "missing_items": missing_legacy,
            "daily_plan": daily_plan,
            "alerts": missing_alerts + weather_alerts,
            "summary": summary_text,
            "notes": notes,
            "take_from_your_closet": take_from_closet,
            "you_might_still_need": still_need,
            "closet_hint": "Add closet items to get personalized packing recommendations."
            if not closet_items
            else None,
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
        items_out = [
            {
                "name": "Travel essentials",
                "category": "essentials",
                "quantity": 1,
                "reason": "Add wardrobe items",
                "available_in_closet": False,
            }
        ]

    take_from_closet = [
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
        # Rules-based fallback because the AI planner was unavailable — the UI can
        # surface a "smart list (planner offline)" hint.
        "degraded": True,
    }
