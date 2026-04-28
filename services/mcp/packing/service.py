"""Packing list service — builds trip packing lists from wardrobe + weather."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, timedelta

import httpx

from shared.schemas import (
    ClosetItem,
    DailyOutfitPlan,
    PackingItem,
    PackingResult,
    WeatherDay,
    WeatherSummary,
)
from shared.logger import get_logger

logger = get_logger("packing.service")

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# ── Category requirements by trip purpose ─────────────────────────────────────

_PURPOSE_CATEGORIES: dict[str, list[str]] = {
    "business": ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "leisure":  ["tops", "bottoms", "shoes", "outerwear"],
    "beach":    ["tops", "bottoms", "shoes", "accessories"],
    "sport":    ["tops", "bottoms", "shoes"],
    "formal":   ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "adventure":["tops", "bottoms", "shoes", "outerwear"],
}

# Category aliases for flexible matching
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
        PackingItem(name="Compact umbrella",  category="accessories", quantity=1, reason="Rain protection"),
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
        PackingItem(name="Swimwear",          category="essentials", quantity=2, reason="Beach activity"),
        PackingItem(name="Beach towel",       category="essentials", quantity=1, reason="Beach use"),
        PackingItem(name="Flip-flops",        category="shoes",      quantity=1, reason="Beach footwear"),
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


def _required_categories(purpose: str, weather_summary: WeatherSummary) -> list[str]:
    key = purpose.lower()
    cats = list(_PURPOSE_CATEGORIES.get(key, ["tops", "bottoms", "shoes"]))
    if weather_summary.dominant_condition in _COLD_CONDITIONS or weather_summary.avg_high < 10:
        if "outerwear" not in cats:
            cats.append("outerwear")
    return cats


def _match_closet(
    closet_items: list[ClosetItem],
    required_categories: list[str],
    trip_days: int,
) -> tuple[list[PackingItem], list[PackingItem]]:
    """Split wardrobe into matched (available) and missing items."""
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
            selected = available[:needed]
            for item in selected:
                matched.append(PackingItem(
                    name=item.name,
                    category=cat,
                    quantity=1,
                    reason=f"From your wardrobe — suits the trip",
                    available_in_closet=True,
                    closet_item_id=item.id,
                ))
        else:
            missing.append(PackingItem(
                name=f"{cat.title()} (not in wardrobe)",
                category=cat,
                quantity=needed,
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
    if dom in {"Sunny"} or weather_summary.avg_high >= 28:
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
    weather_summary: WeatherSummary,
    packing_list: list[PackingItem],
) -> str:
    """Ask GPT-4o for a 2-sentence trip packing summary."""
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
        f"Items packed: {len(packing_list)}. Be concise and encouraging."
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _OPENAI_URL,
                json={
                    "model": _MODEL,
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("ai_summary_error", error=str(exc))
        return f"{purpose.title()} packing list for {destination} — {len(packing_list)} items ready."


async def generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[ClosetItem],
    weather_summary: WeatherSummary,
) -> PackingResult:
    """
    Build a full trip packing list.

    Args:
        destination:     Travel destination name.
        start_date:      Trip start (YYYY-MM-DD).
        end_date:        Trip end (YYYY-MM-DD).
        purpose:         Trip type: business, leisure, beach, sport, formal, adventure.
        closet_items:    User's wardrobe.
        weather_summary: WeatherSummary from the weather MCP server.

    Returns:
        PackingResult with packing_list, missing_items, daily_plan, alerts, summary.
    """
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    trip_days = max(1, (end - start).days + 1)

    required_cats = _required_categories(purpose, weather_summary)
    matched, missing = _match_closet(closet_items, required_cats, trip_days)
    extras = _weather_extras(weather_summary, purpose)
    essentials = list(_ESSENTIALS)
    # Scale essentials to trip length
    for e in essentials:
        if e.category == "essentials" and e.quantity > 1:
            e.quantity = min(e.quantity, trip_days + 1)

    full_list = essentials + matched + extras
    daily_plan = _build_daily_plan(matched, weather_summary, start_date, end_date)
    alerts = _build_alerts(missing, weather_summary, trip_days)
    summary = await _ai_summary(destination, purpose, weather_summary, full_list)

    return PackingResult(
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        purpose=purpose,
        packing_list=full_list,
        missing_items=missing,
        daily_plan=daily_plan,
        alerts=alerts,
        summary=summary,
    )
