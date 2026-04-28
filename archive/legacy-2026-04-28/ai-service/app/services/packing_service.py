"""
Travel packing agent.

Pipeline:
  1. Fetch weather per day  (weather_service)
  2. Determine required clothing categories based on weather + purpose
  3. Compare required items vs user's closet  → find missing items
  4. Build daily outfit plan
  5. Return packing list, missing items, alerts, daily plan
"""
import json
import re
from datetime import date, timedelta
from openai import OpenAI
from app.core.config import settings
from app.models.schemas import (
    ClosetItem, PackingItem, DailyOutfitPlan, PackingResponse, WeatherDay,
)
from app.services.weather_service import fetch_weather, summarise_weather

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# ── Required items logic ────────────────────────────────────

def _required_categories(weather_days: list[WeatherDay], purpose: str) -> list[dict]:
    """Return list of {category, reason, quantity} dicts based on trip conditions."""
    duration = len(weather_days)
    avg_temp = sum(d.temp_high for d in weather_days) / max(len(weather_days), 1)
    rainy = sum(1 for d in weather_days if "rain" in d.condition or "snow" in d.condition)
    formal = purpose in ("business", "conference", "wedding", "formal")
    beach = purpose in ("beach", "holiday", "resort")

    required = [
        {"category": "tops", "reason": "Daily wear", "quantity": min(duration, 7)},
        {"category": "bottoms", "reason": "Daily wear", "quantity": min(duration // 2 + 1, 5)},
        {"category": "shoes", "reason": "Essential footwear", "quantity": 2},
        {"category": "innerwear", "reason": "Innerwear/socks", "quantity": duration},
    ]

    if avg_temp < 15:
        required.append({"category": "outerwear", "reason": "Cold weather — jacket/coat needed", "quantity": 1})
        required.append({"category": "sweater", "reason": "Layering for cold", "quantity": 2})

    if rainy > 0:
        required.append({"category": "rain_jacket", "reason": f"Rain expected on {rainy} day(s)", "quantity": 1})

    if formal:
        required.append({"category": "formal_wear", "reason": f"Formal purpose: {purpose}", "quantity": 2})
        required.append({"category": "formal_shoes", "reason": "Formal footwear", "quantity": 1})

    if beach:
        required.append({"category": "swimwear", "reason": "Beach/resort trip", "quantity": 2})
        required.append({"category": "sandals", "reason": "Beach footwear", "quantity": 1})

    return required


def _match_closet(required: list[dict], closet: list[ClosetItem]) -> tuple[list[PackingItem], list[PackingItem]]:
    """Split required items into available (from closet) and missing."""
    category_map: dict[str, list[ClosetItem]] = {}
    for item in closet:
        cat = (item.category or "other").lower()
        category_map.setdefault(cat, []).append(item)

    packing: list[PackingItem] = []
    missing: list[PackingItem] = []

    for req in required:
        cat = req["category"].lower()
        # Fuzzy match: rain_jacket → outerwear, formal_wear → tops/dresses, etc.
        ALIASES = {
            "rain_jacket": ["outerwear", "jackets"],
            "formal_wear": ["tops", "dresses", "shirts", "blouses"],
            "formal_shoes": ["shoes"],
            "sweater": ["outerwear", "tops", "knitwear"],
            "sandals": ["shoes"],
            "innerwear": ["accessories", "innerwear"],
            "swimwear": ["swimwear", "activewear"],
        }
        candidates = category_map.get(cat, [])
        if not candidates:
            for alias in ALIASES.get(cat, []):
                candidates = category_map.get(alias, [])
                if candidates:
                    break

        if candidates:
            chosen = candidates[:req["quantity"]]
            for c in chosen:
                packing.append(PackingItem(
                    name=c.name,
                    category=req["category"],
                    quantity=1,
                    reason=req["reason"],
                    available_in_closet=True,
                    closet_item_id=c.id,
                ))
        else:
            missing.append(PackingItem(
                name=f"{req['category'].replace('_', ' ').title()} (x{req['quantity']})",
                category=req["category"],
                quantity=req["quantity"],
                reason=req["reason"],
                available_in_closet=False,
            ))

    return packing, missing


def _build_daily_plan(
    weather_days: list[WeatherDay],
    closet: list[ClosetItem],
    purpose: str,
) -> list[DailyOutfitPlan]:
    tops = [i for i in closet if (i.category or "").lower() in ("tops", "shirts", "blouses", "dresses")]
    bottoms = [i for i in closet if (i.category or "").lower() in ("bottoms", "pants", "jeans", "skirts")]
    outerwear = [i for i in closet if (i.category or "").lower() in ("outerwear", "jackets")]

    plan = []
    for idx, day in enumerate(weather_days):
        top = tops[idx % len(tops)] if tops else None
        bottom = bottoms[idx % len(bottoms)] if bottoms else None
        jacket = outerwear[0] if (day.temp_high < 18 and outerwear) else None

        items_needed = []
        parts = []
        if top:
            items_needed.append(top.name)
            parts.append(f"{top.color or ''} {top.name}".strip())
        if bottom:
            items_needed.append(bottom.name)
            parts.append(bottom.name)
        if jacket:
            items_needed.append(jacket.name)
            parts.append(f"{jacket.name} (cold weather)")

        suggestion = (
            f"Day {idx + 1}: {day.description}. "
            f"Outfit: {', '.join(parts) if parts else 'Pack versatile basics'}."
        )

        plan.append(DailyOutfitPlan(
            date=day.date,
            weather=day,
            outfit_suggestion=suggestion,
            items_needed=items_needed,
        ))
    return plan


def _build_alerts(
    missing: list[PackingItem],
    weather_summary: dict,
    duration: int,
) -> list[str]:
    alerts = []
    if len(missing) >= 3:
        alerts.append(f"⚠️  You are underprepared for this trip — {len(missing)} essential item type(s) missing from your wardrobe.")
    if weather_summary.get("rainy_days", 0) > 0:
        has_rain = any("rain" in m.category.lower() for m in missing)
        if has_rain:
            alerts.append(f"🌧  Rain expected on {weather_summary['rainy_days']} day(s) and no rain jacket found in your closet.")
    if weather_summary.get("avg_high", 20) < 10:
        cold_ok = not any("outerwear" in m.category or "sweater" in m.category for m in missing)
        if not cold_ok:
            alerts.append("🧥  Cold destination — ensure you have warm layers.")
    if duration > 7 and len(missing) == 0:
        alerts.append("✅  Your wardrobe looks well-prepared for this trip!")
    return alerts


# ── AI-enhanced packing (optional enrichment) ───────────────

PACKING_AI_PROMPT = """
You are a smart travel packing AI.

Destination: {destination}
Travel dates: {start_date} to {end_date} ({duration} days)
Purpose: {purpose}
Weather summary: {weather_summary}

User's closet ({closet_count} items):
{closet_summary}

Current packing list:
{packing_list}

Missing items:
{missing_list}

Provide a short, actionable packing summary and any extra tips the user should know.
Respond in JSON: {{"summary": "...", "extra_tips": ["tip1", "tip2"]}}
"""


def _ai_enrich(payload: dict) -> dict:
    if not settings.openai_api_key:
        return {}
    try:
        client = _get_client()
        prompt = PACKING_AI_PROMPT.format(**payload)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.5,
        )
        raw = re.sub(r"```(?:json)?", "", response.choices[0].message.content).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[PackingService] AI enrichment failed: {e}")
        return {}


# ── Public entry point ──────────────────────────────────────

def generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[ClosetItem],
) -> PackingResponse:
    # 1. Fetch weather
    weather_days = fetch_weather(destination, start_date, end_date)
    weather_summary = summarise_weather(weather_days)
    duration = len(weather_days)

    # 2. Determine required items
    required = _required_categories(weather_days, purpose)

    # 3. Match against closet
    packing, missing = _match_closet(required, closet_items)

    # 4. Daily plan
    daily_plan = _build_daily_plan(weather_days, closet_items, purpose)

    # 5. Alerts
    alerts = _build_alerts(missing, weather_summary, duration)

    # 6. Optional AI enrichment (adds tips to alerts)
    closet_summary = "\n".join(
        f"- {i.name} ({i.category})" for i in closet_items[:20]
    )
    packing_list_str = "\n".join(f"- {p.name}" for p in packing)
    missing_str = "\n".join(f"- {m.name}: {m.reason}" for m in missing) or "None"

    ai_extra = _ai_enrich({
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "duration": duration,
        "purpose": purpose,
        "weather_summary": json.dumps(weather_summary),
        "closet_count": len(closet_items),
        "closet_summary": closet_summary,
        "packing_list": packing_list_str,
        "missing_list": missing_str,
    })

    if ai_extra.get("summary"):
        alerts.insert(0, f"💡  {ai_extra['summary']}")
    alerts.extend([f"📌  {t}" for t in ai_extra.get("extra_tips", [])])

    packing_ids = [p.closet_item_id for p in packing if p.closet_item_id]

    return PackingResponse(
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        duration_days=duration,
        trip_type=purpose,
        weather_summary=weather_summary,
        packing_list=packing,
        missing_items=missing,
        daily_plan=daily_plan,
        alerts=alerts,
        packing_item_ids=packing_ids,
    )
