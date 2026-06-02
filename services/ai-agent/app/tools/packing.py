"""Packing tool — trip packing lists from wardrobe + weather, as LangChain tools."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, timedelta

import httpx
from langchain_core.tools import tool

from app.tools.schemas import (
    ClosetItem, DailyOutfitPlan, PackingItem, PackingResult, WeatherDay, WeatherSummary,
)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

_PURPOSE_CATEGORIES: dict[str, list[str]] = {
    "business":  ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "leisure":   ["tops", "bottoms", "shoes", "outerwear"],
    "beach":     ["tops", "bottoms", "shoes", "accessories"],
    "sport":     ["tops", "bottoms", "shoes"],
    "formal":    ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "adventure": ["tops", "bottoms", "shoes", "outerwear"],
    # Default when no specific activity is given — versatile everyday coverage.
    "general":   ["tops", "bottoms", "shoes", "outerwear", "accessories"],
}

# Purposes recognised by the tool. Anything else is treated as "general".
_KNOWN_PURPOSES: frozenset[str] = frozenset(_PURPOSE_CATEGORIES)
_DEFAULT_PURPOSE = "general"

_ALIASES: dict[str, list[str]] = {
    "tops":       ["top", "shirt", "t-shirt", "blouse", "sweater", "hoodie", "tee", "knitwear"],
    "bottoms":    ["bottom", "pant", "trouser", "jeans", "skirt", "shorts", "chinos"],
    "shoes":      ["shoe", "sneaker", "boot", "sandal", "loafer", "heel", "trainer"],
    "outerwear":  ["jacket", "coat", "blazer", "cardigan", "outerwear", "trench", "parka"],
    "dresses":    ["dress", "jumpsuit", "romper"],
    "accessories":["bag", "hat", "scarf", "belt", "watch", "jewellery", "sunglasses"],
}

_ESSENTIALS = [
    PackingItem(name="Underwear",      category="essentials", quantity=7, reason="Daily essential"),
    PackingItem(name="Socks",          category="essentials", quantity=7, reason="Daily essential"),
    PackingItem(name="Sleepwear",      category="essentials", quantity=2, reason="Night comfort"),
    PackingItem(name="Toiletry bag",   category="essentials", quantity=1, reason="Personal hygiene"),
    PackingItem(name="Phone charger",  category="essentials", quantity=1, reason="Electronics"),
    PackingItem(name="Travel adapter", category="essentials", quantity=1, reason="Power compatibility"),
]

_WEATHER_EXTRAS: dict[str, list[PackingItem]] = {
    "rainy": [
        PackingItem(name="Compact umbrella",     category="accessories", quantity=1, reason="Rain protection"),
        PackingItem(name="Waterproof bag cover", category="accessories", quantity=1, reason="Bag protection"),
    ],
    "cold": [
        PackingItem(name="Thermal undershirt", category="essentials", quantity=2, reason="Insulation layer"),
        PackingItem(name="Thermal leggings",   category="essentials", quantity=2, reason="Insulation layer"),
        PackingItem(name="Beanie / warm hat",  category="accessories", quantity=1, reason="Head warmth"),
        PackingItem(name="Gloves",             category="accessories", quantity=1, reason="Hand warmth"),
    ],
    "sunny": [
        PackingItem(name="Sunscreen SPF 50+", category="essentials", quantity=1, reason="UV protection"),
        PackingItem(name="Sunglasses",        category="accessories", quantity=1, reason="Eye protection"),
        PackingItem(name="Sun hat",           category="accessories", quantity=1, reason="Sun protection"),
    ],
    "beach": [
        PackingItem(name="Swimwear",    category="essentials", quantity=2, reason="Beach activity"),
        PackingItem(name="Beach towel", category="essentials", quantity=1, reason="Beach use"),
        PackingItem(name="Flip-flops",  category="shoes",      quantity=1, reason="Beach footwear"),
    ],
}

_RAINY_CONDITIONS = {"Rainy", "Showers", "Humid", "Thunderstorms", "Drizzle"}
_COLD_CONDITIONS  = {"Snowy", "Freezing", "Cold"}


def _normalise_category(category: str) -> str:
    cat = category.lower().strip()
    for canonical, aliases in _ALIASES.items():
        if cat == canonical or any(a in cat for a in aliases):
            return canonical
    return cat


def _normalise_purpose(purpose: str) -> str:
    """Map an unrecognised or empty purpose to the general-purpose default."""
    p = (purpose or "").lower().strip()
    return p if p in _KNOWN_PURPOSES else _DEFAULT_PURPOSE


def _required_categories(purpose: str, weather_summary: WeatherSummary) -> list[str]:
    cats = list(_PURPOSE_CATEGORIES.get(_normalise_purpose(purpose), _PURPOSE_CATEGORIES[_DEFAULT_PURPOSE]))
    if weather_summary.dominant_condition in _COLD_CONDITIONS or weather_summary.avg_high < 10:
        if "outerwear" not in cats:
            cats.append("outerwear")
    return cats


def _match_closet(
    closet_items: list[ClosetItem],
    required_categories: list[str],
    trip_days: int,
) -> tuple[list[PackingItem], list[PackingItem]]:
    by_cat: dict[str, list[ClosetItem]] = defaultdict(list)
    for item in closet_items:
        norm = _normalise_category(item.category)
        by_cat[norm].append(item)

    matched: list[PackingItem] = []
    missing: list[PackingItem] = []
    for cat in required_categories:
        available = by_cat.get(cat, [])
        needed = max(1, min(trip_days // 2, 4))
        if available:
            for item in available[:needed]:
                matched.append(PackingItem(
                    name=item.name, category=cat, quantity=1,
                    reason="From your wardrobe — suits the trip",
                    available_in_closet=True, closet_item_id=item.id,
                ))
        else:
            missing.append(PackingItem(
                name=f"{cat.title()} (not in wardrobe)", category=cat, quantity=needed,
                reason=f"You have no {cat} packed — consider purchasing",
                available_in_closet=False,
            ))
    return matched, missing


def _weather_extras(weather_summary: WeatherSummary, purpose: str) -> list[PackingItem]:
    extras: list[PackingItem] = []
    dom = weather_summary.dominant_condition
    if dom in _RAINY_CONDITIONS or weather_summary.rainy_days >= 2:
        extras.extend(_WEATHER_EXTRAS["rainy"])
    if dom in _COLD_CONDITIONS or weather_summary.avg_high < 10:
        extras.extend(_WEATHER_EXTRAS["cold"])
    if dom == "Sunny" or weather_summary.avg_high >= 28:
        extras.extend(_WEATHER_EXTRAS["sunny"])
    if purpose.lower() in {"beach", "leisure"}:
        extras.extend(_WEATHER_EXTRAS["beach"])
    return extras


def _build_daily_plan(
    matched_items: list[PackingItem],
    weather_summary: WeatherSummary,
    start_date: str,
    end_date: str,
) -> list[DailyOutfitPlan]:
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    days  = weather_summary.days or []
    plans: list[DailyOutfitPlan] = []
    tops    = [p.name for p in matched_items if p.category == "tops"]
    bottoms = [p.name for p in matched_items if p.category == "bottoms"]
    shoes   = [p.name for p in matched_items if p.category == "shoes"]
    for i in range((end - start).days + 1):
        current = start + timedelta(days=i)
        weather_day = days[i] if i < len(days) else None
        day_items = []
        if tops:    day_items.append(tops[i % len(tops)])
        if bottoms: day_items.append(bottoms[i % len(bottoms)])
        if shoes:   day_items.append(shoes[i % len(shoes)])
        if weather_day:
            plans.append(DailyOutfitPlan(
                date=current.isoformat(),
                weather=weather_day,
                outfit_name=f"Day {i + 1} — {weather_day.condition} Look",
                items=day_items,
            ))
    return plans


def _build_alerts(
    missing_items: list[PackingItem],
    weather_summary: WeatherSummary,
    trip_days: int,
) -> list[str]:
    alerts: list[str] = []
    if missing_items:
        cats = ", ".join({m.category for m in missing_items})
        alerts.append(f"Missing wardrobe categories: {cats}. Consider purchasing or borrowing.")
    if weather_summary.rainy_days >= trip_days // 2:
        alerts.append("More than half of your trip days expect rain — waterproof gear is essential.")
    if weather_summary.avg_high >= 35:
        alerts.append("Extreme heat expected — prioritise hydration and UV protection.")
    if weather_summary.avg_low < 0:
        alerts.append("Sub-zero nights expected — pack thermal layers and insulated footwear.")
    return alerts


async def _ai_summary(
    destination: str,
    purpose: str,
    notes: str,
    weather_summary: WeatherSummary,
    packing_list: list[PackingItem],
) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return (
            f"Packing list for your {purpose} trip to {destination}. "
            f"Expect {weather_summary.dominant_condition.lower()} conditions with highs of "
            f"{weather_summary.avg_high:.0f}°C."
        )
    prompt = (
        f"Write a 2-sentence friendly packing summary for a {purpose} trip to {destination}. "
        f"Weather: {weather_summary.dominant_condition}, avg {weather_summary.avg_high:.0f}°C. "
        f"Trip notes: {notes or 'none'}. Items packed: {len(packing_list)}. Be concise and encouraging."
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _OPENAI_URL,
                json={"model": _MODEL, "max_tokens": 100,
                      "messages": [{"role": "user", "content": prompt}]},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return f"{purpose.title()} packing list for {destination} — {len(packing_list)} items ready."


async def _generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[ClosetItem],
    weather_summary: WeatherSummary,
    notes: str = "",
) -> PackingResult:
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    trip_days = max(1, (end - start).days + 1)
    required_cats = _required_categories(purpose, weather_summary)
    matched, missing = _match_closet(closet_items, required_cats, trip_days)
    extras = _weather_extras(weather_summary, purpose)
    essentials = [p.model_copy() for p in _ESSENTIALS]
    for e in essentials:
        if e.category == "essentials" and e.quantity > 1:
            e.quantity = min(e.quantity, trip_days + 1)
    full_list = sorted(essentials + matched + extras, key=lambda item: item.category)
    daily_plan = _build_daily_plan(matched, weather_summary, start_date, end_date)
    alerts = _build_alerts(missing, weather_summary, trip_days)
    summary = await _ai_summary(destination, purpose, notes, weather_summary, full_list)
    return PackingResult(
        destination=destination, start_date=start_date, end_date=end_date, purpose=purpose,
        packing_list=full_list, missing_items=missing, daily_plan=daily_plan,
        alerts=alerts, summary=summary,
    )


# ── LangChain tools ───────────────────────────────────────────────────────────

@tool
async def generate_trip_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items_json: str,
    weather_summary_json: str,
    notes: str = "",
) -> str:
    """
    Generate a complete packing list for a trip.

    Args:
        destination:          City / country name.
        start_date:           Trip start date (YYYY-MM-DD).
        end_date:             Trip end date (YYYY-MM-DD).
        purpose:              Trip type: business, leisure, beach, sport, formal,
                              adventure, or general. When the user does not state
                              an activity, pass "general" for a versatile everyday
                              packing list — do not leave it blank.
        closet_items_json:    JSON array of closet items from the user's wardrobe.
        weather_summary_json: JSON WeatherSummary from get_weather_summary (call that first).

    Returns:
        JSON PackingResult with packing_list, missing_items, daily_plan, alerts, summary.
    """
    # Destination and dates are required; purpose defaults to a general-purpose visit.
    for field, val in [
        ("destination", destination), ("start_date", start_date),
        ("end_date", end_date),
    ]:
        if not val.strip():
            return json.dumps({"error": f"{field} cannot be empty"})
    purpose = _normalise_purpose(purpose)
    if start_date > end_date:
        return json.dumps({"error": "start_date must be before end_date"})
    try:
        raw_items = json.loads(closet_items_json) if closet_items_json.strip() else []
        closet_items = [ClosetItem(**item) for item in raw_items]
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid closet_items_json: {exc}"})
    try:
        weather_summary = WeatherSummary(**json.loads(weather_summary_json))
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid weather_summary_json: {exc}"})
    try:
        result = await _generate_packing_list(
            destination=destination, start_date=start_date, end_date=end_date,
            purpose=purpose, notes=notes, closet_items=closet_items,
            weather_summary=weather_summary,
        )
        return result.model_dump_json(indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
async def get_packing_checklist(
    destination: str,
    purpose: str,
    duration_days: int,
    avg_temperature: float = 20.0,
) -> str:
    """
    Return a simple generic packing checklist without wardrobe matching.

    Args:
        destination:     Travel destination.
        purpose:         Trip type.
        duration_days:   Number of days.
        avg_temperature: Average temperature in Celsius (default 20).

    Returns:
        JSON object with a checklist array of item strings.
    """
    if not destination.strip() or not purpose.strip():
        return json.dumps({"error": "destination and purpose are required"})
    days = max(1, duration_days)
    items: list[str] = [
        f"Underwear × {days}", f"Socks × {days}",
        f"T-shirts / tops × {max(3, days // 2)}",
        f"Bottoms (trousers / jeans) × {max(2, days // 3)}",
        "Comfortable walking shoes", "Sleepwear × 2",
        "Toiletries bag", "Phone charger + travel adapter",
        "Reusable water bottle", "Passport / ID + travel documents",
    ]
    if purpose.lower() == "business":
        items += ["Formal shirt × 2", "Suit / blazer", "Dress shoes", "Business cards"]
    if purpose.lower() in {"beach", "leisure"} or avg_temperature >= 28:
        items += ["Swimwear × 2", "Sunscreen SPF 50+", "Sunglasses", "Beach towel", "Flip-flops"]
    if avg_temperature < 10:
        items += ["Heavy jacket / coat", "Thermal layers × 2", "Gloves", "Beanie"]
    if avg_temperature < 0:
        items += ["Insulated waterproof boots", "Scarf"]
    return json.dumps({"checklist": items, "destination": destination, "duration_days": days}, indent=2)
