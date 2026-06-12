"""
Activity-aware travel packing service — LLM calls and orchestration.

Generates a day-by-day outfit planner driven by planned activities,
bag size constraints, weather, user style profile, and real closet items.

Supporting pieces live in sibling modules (re-exported here):
  packing_constants    — category aliases, purpose sets, bag-size tables
  packing_formatting   — prompt-block formatters (pure)
  packing_postprocess  — AI-output normalisation, checklist, alerts
  packing_fallback     — deterministic rule-based plans when AI is unavailable
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any

from langsmith import traceable
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.llm_safety import sanitize_user_text
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.services.location_intel_service import build_location_context_block
from app.services.packing_constants import (  # noqa: F401  (re-exported)
    BAG_CONSTRAINTS,
    _CATEGORY_ALIASES,
    _PURPOSE_CATEGORIES,
    _get_bag_constraints,
    _normalise_category,
)
from app.services.packing_fallback import (  # noqa: F401  (re-exported)
    _minimal_packing_fallback,
    _rule_based_day_plans,
    _rule_based_packing_sections,
)
from app.services.packing_formatting import (  # noqa: F401  (re-exported)
    _format_activities_for_prompt,
    _format_closet_for_prompt,
    _per_day_weather_table,
)
from app.services.packing_postprocess import (  # noqa: F401  (re-exported)
    _build_legacy_daily_plan,
    _build_packing_checklist,
    _enrich_day_plans_with_images,
    _normalise_packing_output,
    _weather_alerts,
)
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
- Trip style: {trip_style or 'not specified'}
- Bag size: {bag['label']}
- Weather: {weather_text}
{per_day_block}
- Notes: {notes or 'None'}
{location_block}{style_block}
PLANNED ACTIVITIES:
{activities_block}

BAG SIZE CONSTRAINT: {bag['hint']}

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
    safe_purpose     = sanitize_user_text(purpose, field="notes", max_len=80)
    safe_notes       = sanitize_user_text(notes or "", field="trip_notes") or "None"

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
            logger.warning("packing_weather_fallback", destination=destination,
                           data_source=weather_summary.get("data_source"))

        merged_ctx = style_profile_context_text
        if merged_ctx is None and user_style_profile:
            merged_ctx = user_style_profile.get("style_profile_context_text")

        # ── Destination location preferences (curated profile or LLM fallback) ─
        location_context = build_location_context_block(destination, mode="travel")

        # ── New activity-aware AI call ────────────────────────────────────────
        ai_rich = await _ai_activity_aware_packing(
            destination, start_date, end_date, purpose, trip_style, bag_size,
            trip_days, closet_items, weather_summary, weather_days, activities, notes,
            style_profile_context_text=merged_ctx,
            rag_context=rag_context,
            location_context=location_context,
        )

        # ── Legacy AI call for backward-compat take_from / you_might_need ────
        ai_legacy = await _ai_packing_recommendations(
            destination, start_date, end_date, purpose, trip_days,
            closet_items, weather_summary, notes,
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
            day_plans_rich = _rule_based_day_plans(
                closet_items, activities, start_date, trip_days, weather_days
            )

        # ── Process legacy AI output ──────────────────────────────────────────
        if ai_legacy:
            take_from_closet, still_need = _normalise_packing_output(ai_legacy, closet_items)
        else:
            take_from_closet, still_need = _rule_based_packing_sections(
                closet_items, purpose, trip_days, weather_summary,
            )

        # ── Build checklist ───────────────────────────────────────────────────
        packing_checklist = _build_packing_checklist(day_plans_rich, missing_items_rich, trip_days)

        # ── Legacy packing_list (rule-based, backward compat) ─────────────────
        by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in closet_items:
            by_category[_normalise_category(str(item.get("category", "")))].append(item)

        packing_list: list[dict[str, Any]] = [
            {"name": "Underwear",     "category": "essentials", "quantity": trip_days, "reason": "Daily essential", "available_in_closet": False},
            {"name": "Socks",         "category": "essentials", "quantity": trip_days, "reason": "Daily essential", "available_in_closet": False},
            {"name": "Phone charger", "category": "essentials", "quantity": 1,         "reason": "Electronics",     "available_in_closet": False},
        ]
        missing_legacy: list[dict[str, Any]] = []
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
                missing_legacy.append({
                    "name": f"{category.title()} (not in wardrobe)",
                    "category": category,
                    "quantity": 1,
                    "reason": f"No {category} found",
                    "available_in_closet": False,
                })

        avg_high = weather_summary.get("avg_high", 20)
        avg_low = weather_summary.get("avg_low", 10)
        dominant = (weather_summary.get("dominant_condition") or "").lower()
        if weather_summary.get("rainy_days"):
            packing_list.append({"name": "Compact umbrella", "category": "accessories", "quantity": 1, "reason": "Rain protection", "available_in_closet": False})
        if avg_high >= 28 or purpose == "beach":
            packing_list.append({"name": "Sunscreen SPF 50+", "category": "essentials", "quantity": 1, "reason": "Sun protection", "available_in_closet": False})
            packing_list.append({"name": "Sunglasses", "category": "accessories", "quantity": 1, "reason": "Eye protection", "available_in_closet": False})
        if avg_high <= 12 or any(w in dominant for w in ("cold", "snow", "freez")):
            packing_list.append({"name": "Thermal base layer", "category": "essentials", "quantity": 2, "reason": f"Cold weather ({avg_high:.0f}°C)", "available_in_closet": False})
        if avg_low < 0 or "snow" in dominant:
            packing_list.append({"name": "Heavy insulated coat", "category": "outerwear", "quantity": 1, "reason": f"Sub-zero/snowy ({avg_low:.0f}°C)", "available_in_closet": False})
        if purpose == "beach":
            packing_list.append({"name": "Swimwear", "category": "essentials", "quantity": 2, "reason": "Beach trip essential", "available_in_closet": False})

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
            "closet_hint": "Add closet items to get personalized packing recommendations." if not closet_items else None,
        }
    except Exception as exc:
        logger.warning("packing_generation_fallback", error=str(exc), destination=destination)
        return _minimal_packing_fallback(destination, start_date, end_date, purpose, closet_items, notes)
