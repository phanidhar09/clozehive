"""
Packing service — builds a smart travel packing list.

Pipeline:
  1. Receive pre-fetched weather summary (passed in by the agent/caller)
  2. Determine required clothing categories based on weather + trip purpose
  3. Match required items against the user's closet
  4. Build a daily outfit plan
  5. Optionally enrich with GPT tips
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from openai import AsyncOpenAI

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import (
    ClosetItem,
    DailyOutfitPlan,
    PackingItem,
    PackingResult,
    WeatherDay,
    WeatherSummary,
)

logger = get_logger(__name__)

# ── Category alias map ────────────────────────────────────────────────────────

_ALIASES: dict[str, list[str]] = {
    "t-shirt":      ["t-shirt", "tshirt", "tee", "top", "shirt"],
    "shirt":        ["shirt", "blouse", "button-down", "top"],
    "pants":        ["pants", "trousers", "jeans", "chinos", "leggings"],
    "shorts":       ["shorts", "bermuda"],
    "dress":        ["dress", "sundress", "midi", "maxi"],
    "skirt":        ["skirt", "mini", "midi skirt"],
    "jacket":       ["jacket", "blazer", "coat", "windbreaker", "anorak"],
    "rain jacket":  ["rain jacket", "raincoat", "waterproof", "mac"],
    "sweater":      ["sweater", "jumper", "pullover", "hoodie", "knitwear"],
    "underwear":    ["underwear", "boxer", "brief", "bra", "lingerie"],
    "socks":        ["socks", "sock"],
    "shoes":        ["shoes", "sneakers", "trainers", "loafers", "boots", "sandals", "heels"],
    "swimwear":     ["swimwear", "swimsuit", "bikini", "swim trunks", "boardshorts"],
    "formal shirt": ["formal shirt", "dress shirt", "oxford shirt"],
    "suit":         ["suit", "blazer set", "formal set"],
    "thermal":      ["thermal", "base layer", "long underwear"],
    "hat":          ["hat", "cap", "beanie", "sun hat"],
    "sunglasses":   ["sunglasses", "shades"],
}


def _item_matches(item: ClosetItem, target_category: str) -> bool:
    aliases = _ALIASES.get(target_category, [target_category])
    searchable = f"{item.name} {item.category} {' '.join(item.tags)}".lower()
    return any(alias in searchable for alias in aliases)


def _required_categories(
    weather_summary: WeatherSummary,
    purpose: str,
    duration_days: int,
) -> list[tuple[str, int, str]]:
    """
    Return a list of (category, quantity, reason) tuples.
    Quantity is per-trip (not per day) — sane packing amounts.
    """
    avg_high = weather_summary.avg_high
    rainy = weather_summary.rainy_days > 0
    purpose_lower = purpose.lower()

    is_beach  = any(w in purpose_lower for w in ["beach", "resort", "tropical", "holiday"])
    is_formal = any(w in purpose_lower for w in ["conference", "business", "wedding", "formal"])
    is_hike   = any(w in purpose_lower for w in ["hiking", "trek", "outdoor", "camping"])

    reqs: list[tuple[str, int, str]] = [
        ("underwear", min(duration_days, 7), "Daily essential"),
        ("socks",     min(duration_days, 7), "Daily essential"),
    ]

    shirts_qty = max(2, min(duration_days, 5))
    pants_qty  = max(2, min(duration_days // 2 + 1, 4))

    if avg_high >= 25 or is_beach:
        reqs += [
            ("t-shirt",    shirts_qty, "Hot weather staple"),
            ("shorts",     pants_qty,  "Hot weather"),
            ("sunglasses", 1,          "UV protection"),
            ("hat",        1,          "Sun protection"),
        ]
        if is_beach:
            reqs.append(("swimwear", 2, "Beach / pool"))
    elif avg_high >= 15:
        reqs += [
            ("shirt",    shirts_qty, "Mild weather"),
            ("pants",    pants_qty,  "Versatile bottoms"),
            ("sweater",  2,          "Evening layering"),
            ("jacket",   1,          "Light outer layer"),
        ]
    else:
        reqs += [
            ("shirt",    shirts_qty, "Base layer"),
            ("pants",    pants_qty,  "Warm bottoms"),
            ("sweater",  3,          "Insulation"),
            ("jacket",   1,          "Warm outer layer"),
            ("thermal",  2,          "Cold weather base layer"),
        ]

    if rainy:
        reqs.append(("rain jacket", 1, "Rain protection"))

    if is_formal:
        reqs += [
            ("formal shirt", 2, "Business / formal occasions"),
            ("suit",         1, "Formal meetings or events"),
        ]

    if is_hike:
        reqs += [
            ("shoes", 1, "Sturdy hiking footwear"),
            ("hat",   1, "Outdoor sun protection"),
        ]
    else:
        reqs.append(("shoes", 2, "Comfortable walking shoes + backup pair"))

    return reqs


def _match_closet(
    required: list[tuple[str, int, str]],
    closet: list[ClosetItem],
) -> tuple[list[PackingItem], list[str]]:
    packing: list[PackingItem] = []
    missing: list[str] = []

    for category, qty, reason in required:
        matched = [item for item in closet if _item_matches(item, category)]
        if matched:
            for item in matched[:qty]:
                packing.append(
                    PackingItem(
                        name=item.name,
                        category=category,
                        quantity=1,
                        reason=reason,
                        available_in_closet=True,
                        closet_item_id=str(item.id) if item.id else None,
                    )
                )
        else:
            missing.append(f"{qty}x {category} — {reason}")
            packing.append(
                PackingItem(
                    name=f"{category.title()} (to buy)",
                    category=category,
                    quantity=qty,
                    reason=reason,
                    available_in_closet=False,
                )
            )

    return packing, missing


def _build_daily_plan(
    start_date: str,
    end_date: str,
    weather_days: list[WeatherDay],
    packing: list[PackingItem],
) -> list[DailyOutfitPlan]:
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    days: list[DailyOutfitPlan] = []

    available = [p for p in packing if p.available_in_closet]
    tops     = [p for p in available if p.category in ("t-shirt", "shirt", "formal shirt")]
    bottoms  = [p for p in available if p.category in ("pants", "shorts", "skirt")]
    shoes    = [p for p in available if p.category == "shoes"]

    current = start
    idx = 0
    while current <= end:
        weather_day = next(
            (w for w in weather_days if w.date == current.isoformat()),
            None,
        )
        weather_str = weather_day.condition if weather_day else "unknown"

        top    = tops[idx % len(tops)].name    if tops    else "Pack a top"
        bottom = bottoms[idx % len(bottoms)].name if bottoms else "Pack bottoms"
        shoe   = shoes[idx % len(shoes)].name  if shoes   else "Pack shoes"

        days.append(
            DailyOutfitPlan(
                date=current.isoformat(),
                weather=weather_str,
                outfit_suggestion=f"{top} + {bottom} + {shoe}",
                items_needed=[top, bottom, shoe],
            )
        )
        current += timedelta(days=1)
        idx += 1

    return days


def _build_alerts(
    weather_summary: WeatherSummary,
    missing: list[str],
    destination: str,
) -> list[str]:
    alerts: list[str] = []

    if missing:
        alerts.append(f"⚠️  {len(missing)} item(s) not in your closet — consider buying before departure.")

    if weather_summary.rainy_days > 2:
        alerts.append("🌧  Several rainy days expected — waterproof footwear strongly recommended.")

    if weather_summary.avg_high > 35:
        alerts.append("☀️  Extreme heat — apply SPF 50+, stay hydrated, carry a reusable water bottle.")

    if weather_summary.avg_low < 5:
        alerts.append("🥶  Very cold nights — ensure you have thermals and a heavy outer layer.")

    alerts.append(f"📋  Always check latest entry requirements for {destination} before departure.")

    return alerts


async def _ai_enrich(
    result: PackingResult,
    purpose: str,
    weather_summary: WeatherSummary,
) -> PackingResult:
    """Use GPT to add smart packing tips and missing-item suggestions."""
    settings = get_settings()
    if not settings.openai_api_key:
        return result

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = f"""
Trip: {result.destination} | {result.start_date} to {result.end_date}
Purpose: {purpose}
Weather: {weather_summary.dominant_condition}, avg {weather_summary.avg_high}°C high / {weather_summary.avg_low}°C low
Missing items: {", ".join(result.missing_items) or "none"}

Give 3 smart packing tips specific to this trip as a JSON array of strings.
Return ONLY the JSON array, no markdown.
""".strip()

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=300,
            temperature=0.6,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content or "[]"
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        tips: list[str] = json.loads(raw)
        result.alerts = tips + result.alerts
    except Exception as exc:
        logger.warning("AI enrichment skipped: %s", exc)

    return result


async def generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[ClosetItem],
    weather_summary: WeatherSummary,
) -> PackingResult:
    """
    Build a full packing list for a trip.

    Args:
        destination:     Travel destination city / country.
        start_date:      Trip start in YYYY-MM-DD format.
        end_date:        Trip end in YYYY-MM-DD format.
        purpose:         Trip purpose (business / beach / hiking / casual …).
        closet_items:    User's wardrobe items.
        weather_summary: Pre-fetched WeatherSummary from the weather service.

    Returns:
        PackingResult with packing list, daily plan, missing items, and alerts.
    """
    start  = date.fromisoformat(start_date)
    end    = date.fromisoformat(end_date)
    duration_days = (end - start).days + 1

    logger.info(
        "Generating packing list — %s, %d days, purpose=%s, %d closet items",
        destination, duration_days, purpose, len(closet_items),
    )

    # Determine trip type
    purpose_lower = purpose.lower()
    if any(w in purpose_lower for w in ["business", "conference", "work"]):
        trip_type = "business"
    elif any(w in purpose_lower for w in ["beach", "resort", "holiday", "vacation"]):
        trip_type = "leisure"
    elif any(w in purpose_lower for w in ["hike", "trek", "outdoor", "camping"]):
        trip_type = "adventure"
    else:
        trip_type = "general"

    required = _required_categories(weather_summary, purpose, duration_days)
    packing, missing = _match_closet(required, closet_items)
    daily_plan = _build_daily_plan(start_date, end_date, weather_summary.days, packing)
    alerts = _build_alerts(weather_summary, missing, destination)

    packing_item_ids = [p.closet_item_id for p in packing if p.closet_item_id]

    result = PackingResult(
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        duration_days=duration_days,
        trip_type=trip_type,
        weather_summary=weather_summary.model_dump(exclude={"days"}),
        packing_list=packing,
        missing_items=missing,
        daily_plan=daily_plan,
        alerts=alerts,
        packing_item_ids=packing_item_ids,
    )

    result = await _ai_enrich(result, purpose, weather_summary)
    logger.info(
        "Packing list complete — %d items, %d missing, %d alerts",
        len(packing), len(missing), len(alerts),
    )
    return result
