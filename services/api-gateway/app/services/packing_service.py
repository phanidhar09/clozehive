"""Consolidated packing service — rule-based + optional AI personalisation."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from langsmith import traceable
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.services.weather_service import fetch_weather_async, summarise_weather

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

def _per_day_weather_table(weather_days: list[dict[str, Any]]) -> str:
    """Compact per-day weather table for the AI prompt."""
    if not weather_days:
        return ""
    lines = ["Per-day weather forecast:"]
    for i, wd in enumerate(weather_days[:14], 1):
        lines.append(
            f"  Day {i} ({wd.get('date', '?')}): {wd.get('condition', '?')} | "
            f"High {wd.get('temp_high', '?')}°C / Low {wd.get('temp_low', '?')}°C"
        )
    return "\n".join(lines)


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
    """
    Ask the LLM which wardrobe items to pack and what else is needed.
    Returns parsed dict or None when AI is unavailable.
    """
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
        style_block = (
            "\nPersonalisation (respect fit, sizes, preferred colors, climate comfort):\n"
            f"{style_profile_context_text.strip()}\n\n"
        )
    if rag_context and rag_context.strip():
        style_block += f"\nRAG Context (use as additional guidance):\n{rag_context.strip()}\n\n"

    prompt = (
        "You are a professional travel stylist. Help pack for this trip.\n\n"
        "Trip details:\n"
        f"- Destination: {destination}\n"
        f"- Dates: {start_date} to {end_date} ({trip_days} days)\n"
        f"- Purpose: {purpose}\n"
        f"- Weather summary: {weather_text}\n"
        f"{per_day_block}\n"
        f"- Notes: {notes or 'None'}\n"
        f"{style_block}"
        f"User's wardrobe:\n{closet_text}\n\n"
        "From the user's wardrobe, which of these items would you recommend for this trip?\n\n"
        "Return ONLY valid JSON with this exact structure:\n"
        '{"take_from_your_closet": [{"item_id": "<id from wardrobe>", "name": "<exact name>", '
        '"category": "<category>", "reason": "<why it suits this trip and its weather>", '
        '"recommended_days": ["Day 1", "Day 2"]}], '
        '"you_might_still_need": [{"name": "<item>", "category": "<category>", '
        '"reason": "<why needed — mention weather if relevant>"}]}\n\n'
        "Rules:\n"
        "- Only include items from the provided wardrobe in take_from_your_closet.\n"
        "- Do not invent wardrobe items not listed above.\n"
        "- For you_might_still_need: list items the user does NOT own but would help — "
        "include weather-specific gear (rain jacket for rainy days, thermal layers for cold days, "
        "breathable tops for hot/sunny days, etc.).\n"
        "- Assign recommended_days based on the per-day forecast: waterproof items on rainy days, "
        "light breathable items on hot days, warm layers on cold days.\n"
        "- Prefer versatile items reusable across multiple days.\n"
        "- Keep recommendations practical and specific."
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

    avg_high = weather_summary.get("avg_high", 20)
    avg_low = weather_summary.get("avg_low", 10)
    rainy_days = weather_summary.get("rainy_days", 0)
    dominant = (weather_summary.get("dominant_condition") or "").lower()

    if rainy_days >= 1:
        still_need.append({
            "name": "Compact umbrella",
            "category": "accessories",
            "reason": f"Rain expected on {rainy_days} day(s) of the trip.",
        })
        still_need.append({
            "name": "Waterproof jacket / rain mac",
            "category": "outerwear",
            "reason": "Keeps you dry on rainy days.",
        })

    if avg_high >= 28 or purpose == "beach":
        still_need.append({
            "name": "Sunscreen SPF 50+",
            "category": "essentials",
            "reason": "Sun protection for warm/beach conditions.",
        })
        still_need.append({
            "name": "Sunglasses",
            "category": "accessories",
            "reason": "Eye protection in bright sunny conditions.",
        })
        still_need.append({
            "name": "Sun hat",
            "category": "accessories",
            "reason": "Head protection against strong sun.",
        })

    if avg_high <= 12 or any(w in dominant for w in ("cold", "snow", "freez", "frost")):
        still_need.append({
            "name": "Thermal base layer",
            "category": "essentials",
            "reason": f"Cold temperatures expected (avg high {avg_high:.0f}°C).",
        })
        still_need.append({
            "name": "Beanie / warm hat",
            "category": "accessories",
            "reason": "Head warmth for cold weather.",
        })
        still_need.append({
            "name": "Gloves",
            "category": "accessories",
            "reason": "Hand warmth in cold conditions.",
        })

    if avg_low < 0 or "snow" in dominant or "freez" in dominant:
        still_need.append({
            "name": "Heavy insulated coat",
            "category": "outerwear",
            "reason": f"Sub-zero or snowy conditions expected (avg low {avg_low:.0f}°C).",
        })
        still_need.append({
            "name": "Thermal leggings",
            "category": "essentials",
            "reason": "Extra insulation for freezing temperatures.",
        })

    if "wind" in dominant or avg_high < 18:
        still_need.append({
            "name": "Windbreaker / light jacket",
            "category": "outerwear",
            "reason": "Windy or cool conditions — a windbreaker adds comfort.",
        })

    if purpose == "beach":
        still_need.append({
            "name": "Swimwear",
            "category": "essentials",
            "reason": "Beach trip essential.",
        })

    return take_from_closet, still_need


# ── Weather alert builder ─────────────────────────────────────────────────────

def _weather_alerts(weather_summary: dict[str, Any], trip_days: int) -> list[str]:
    alerts: list[str] = []
    avg_high = weather_summary.get("avg_high", 20)
    avg_low = weather_summary.get("avg_low", 10)
    rainy_days = weather_summary.get("rainy_days", 0)
    dominant = (weather_summary.get("dominant_condition") or "").lower()

    if rainy_days >= trip_days // 2:
        alerts.append(f"Rain expected on {rainy_days}/{trip_days} days — waterproof layers are essential.")
    elif rainy_days >= 1:
        alerts.append(f"Rain expected on {rainy_days} day(s) — pack an umbrella and light waterproof layer.")
    if avg_high >= 35:
        alerts.append(f"Extreme heat expected ({avg_high:.0f}°C) — pack breathable fabrics and stay hydrated.")
    elif avg_high >= 28:
        alerts.append(f"Warm weather ({avg_high:.0f}°C) — prioritise light, breathable clothing and sun protection.")
    if avg_low < 0:
        alerts.append(f"Sub-zero nights ({avg_low:.0f}°C) — thermal layers and insulated footwear are a must.")
    elif avg_high <= 12:
        alerts.append(f"Cold conditions (avg high {avg_high:.0f}°C) — bring warm layers and outerwear.")
    if "snow" in dominant:
        alerts.append("Snow forecast — waterproof boots and heavy insulation recommended.")
    return alerts


# ── Daily outfit plan builder ─────────────────────────────────────────────────

def _build_daily_plan(
    take_from_closet: list[dict[str, Any]],
    start_date: str,
    trip_days: int,
    weather_days: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Build a per-day outfit plan. Every day gets an entry with weather context;
    closet items are slotted in based on their recommended_days labels.
    Days without AI-assigned items fall back to a round-robin suggestion.
    Caps at 14 days.
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

    # Round-robin fallback pool when no specific items are assigned
    fallback_pool = take_from_closet or []

    plan: list[dict[str, Any]] = []
    for i in range(min(trip_days, 14)):
        label = f"Day {i + 1}"
        day_date = (start + timedelta(days=i)).isoformat()
        weather = weather_by_date.get(day_date)

        items_for_day = day_map.get(label, [])
        if not items_for_day and fallback_pool:
            # Rotate through available items so each day has something suggested
            items_for_day = [fallback_pool[i % len(fallback_pool)]]

        entry: dict[str, Any] = {
            "date": day_date,
            "day_label": label,
            "outfit_name": (
                f"{label} — {weather['condition']} Look" if weather else f"{label} outfit"
            ),
            "items": [it["name"] for it in items_for_day],
            "item_ids": [it["item_id"] for it in items_for_day if it.get("item_id")],
        }
        if weather:
            entry["weather"] = weather
            entry["weather_note"] = _weather_outfit_note(weather)
        plan.append(entry)

    return plan


def _weather_outfit_note(weather_day: dict[str, Any]) -> str:
    """Short styling tip based on the day's forecast."""
    condition = (weather_day.get("condition") or "").lower()
    high = weather_day.get("temp_high", 20)
    if "rain" in condition or "shower" in condition or "drizzle" in condition:
        return "Rainy day — wear waterproof outer layer and waterproof footwear."
    if "snow" in condition or "freez" in condition:
        return "Snowy/freezing — insulated coat, thermal layers, waterproof boots essential."
    if high >= 30:
        return f"Hot day ({high}°C) — light breathable fabrics, sun hat and sunscreen."
    if high <= 10:
        return f"Cold day ({high}°C) — layer up: thermal base + warm mid-layer + coat."
    if "wind" in condition:
        return "Windy — a windbreaker or fitted jacket will add comfort."
    return f"Mild conditions ({high}°C) — versatile layers work well."


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
    style_profile_context_text: str | None = None,
    user_style_profile: dict[str, Any] | None = None,
    rag_context: str | None = None,
) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        trip_days = max(1, (end - start).days + 1)
        weather_days = await fetch_weather_async(destination, start_date, end_date)
        weather_summary = summarise_weather(weather_days)
        if weather_summary.get("data_source") != "live":
            logger.warning(
                "packing_weather_fallback",
                destination=destination,
                data_source=weather_summary.get("data_source"),
                hint="Weather is estimated from static profiles — packing list may not reflect actual forecast.",
            )

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

        avg_high = weather_summary.get("avg_high", 20)
        avg_low = weather_summary.get("avg_low", 10)
        dominant = (weather_summary.get("dominant_condition") or "").lower()

        if weather_summary["rainy_days"]:
            packing_list.append({"name": "Compact umbrella", "category": "accessories", "quantity": 1, "reason": "Rain protection", "available_in_closet": False})
            packing_list.append({"name": "Waterproof jacket", "category": "outerwear", "quantity": 1, "reason": "Stay dry on rainy days", "available_in_closet": False})
        if avg_high >= 28 or purpose == "beach":
            packing_list.append({"name": "Sunscreen SPF 50+", "category": "essentials", "quantity": 1, "reason": "Sun protection", "available_in_closet": False})
            packing_list.append({"name": "Sunglasses", "category": "accessories", "quantity": 1, "reason": "Eye protection in strong sun", "available_in_closet": False})
        if avg_high <= 12 or any(w in dominant for w in ("cold", "snow", "freez")):
            packing_list.append({"name": "Thermal base layer", "category": "essentials", "quantity": 2, "reason": f"Cold weather (avg high {avg_high:.0f}°C)", "available_in_closet": False})
            packing_list.append({"name": "Warm hat & gloves", "category": "accessories", "quantity": 1, "reason": "Head and hand warmth in cold", "available_in_closet": False})
        if avg_low < 0 or "snow" in dominant:
            packing_list.append({"name": "Heavy insulated coat", "category": "outerwear", "quantity": 1, "reason": f"Sub-zero/snowy conditions (avg low {avg_low:.0f}°C)", "available_in_closet": False})
        if purpose == "beach":
            packing_list.append({"name": "Swimwear", "category": "essentials", "quantity": 2, "reason": "Beach trip essential", "available_in_closet": False})

        # ── New personalised sections ─────────────────────────────────────────
        merged_ctx = style_profile_context_text
        if merged_ctx is None and user_style_profile:
            merged_ctx = user_style_profile.get("style_profile_context_text")
        ai_data = await _ai_packing_recommendations(
            destination, start_date, end_date, purpose, trip_days,
            closet_items, weather_summary, notes,
            style_profile_context_text=merged_ctx,
            weather_days=weather_days,
            rag_context=rag_context,
        )

        if ai_data:
            take_from_closet, still_need = _normalise_packing_output(ai_data, closet_items)
        else:
            take_from_closet, still_need = _rule_based_packing_sections(
                closet_items, purpose, trip_days, weather_summary,
            )

        daily_plan = _build_daily_plan(take_from_closet, start_date, trip_days, weather_days)

        weather_alerts = _weather_alerts(weather_summary, trip_days)
        missing_alerts = [f"Missing: {', '.join({i['category'] for i in missing_items})}"] if missing_items else []

        return {
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "purpose": purpose,
            "duration_days": trip_days,
            "weather_summary": weather_summary,
            "weather_forecast": weather_days,
            # ── Existing fields (backward-compatible) ─────────────────────────
            "packing_list": packing_list,
            "items": packing_list,
            "missing_items": missing_items,
            "daily_plan": daily_plan,
            "alerts": missing_alerts + weather_alerts,
            "summary": (
                f"Packing list for your {purpose} trip to {destination}. "
                f"Expect {weather_summary['dominant_condition'].lower()} conditions "
                f"(avg {weather_summary['avg_high']:.0f}°C / {weather_summary['avg_low']:.0f}°C). "
                f"{weather_summary.get('recommendation', '')}"
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
