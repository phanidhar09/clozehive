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

from app.api.v1.intelligence.services import ai_service, festival_discovery, model_router
from app.api.v1.intelligence.services.model_router import Task
from app.api.v1.travel.services import venue_rules_service
from app.api.v1.travel.services.location_intel_service import (
    build_location_context_block_async,
)
from app.api.v1.travel.services.weather_service import fetch_weather_async, summarise_weather
from app.core.analytics import LLMTelemetry
from app.core.config import get_settings
from app.core.constraint_priority import build_constraint_priority_block
from app.core.llm_safety import sanitize_user_text
from app.core.logging import get_logger

logger = get_logger("packing_service")
settings = get_settings()

_PACKING_SYSTEM_PROMPT = (
    "You are FANI, ClozeHive's travel packing planner. "
    "Respond with valid JSON only that matches the schema in the user message. "
    "Ground every closet item in the provided wardrobe ids — never invent items."
)

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
        for field in ("color", "brand", "fabric", "pattern", "fit", "season", "size", "notes", "condition"):
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


# ── Trip-relevance ranking ─────────────────────────────────────────────────────
# When a closet is large, dumping every item into the prompt bloats tokens and
# dilutes the model's choices. We pre-rank items by how well they fit the trip's
# weather, planned activities, purpose and style, then keep the best per category
# so the model still sees full-outfit coverage but only the relevant candidates.

# Below this many items we send the whole closet untouched — trimming a small
# wardrobe risks removing a piece the model genuinely needs.
_RANK_TRIM_THRESHOLD = 40

_WARM_SEASONS = {"summer", "spring"}
_COLD_SEASONS = {"winter", "fall", "autumn"}
_ALL_SEASON = {"all", "all-season", "all season", "any", "year-round"}


def _as_token_set(value: Any) -> set[str]:
    """Flatten a str | list[str] | None field into a lowercased token set."""
    if not value:
        return set()
    if isinstance(value, str):
        return {value.lower().strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(v).lower().strip() for v in value if v}
    return set()


def _trip_keywords(activities: list[dict[str, Any]], purpose: str, trip_style: str | None) -> set[str]:
    kw: set[str] = set()
    for act in activities or []:
        kw |= _as_token_set(act.get("name"))
        kw |= _as_token_set(act.get("formality"))
    kw |= _as_token_set(purpose)
    kw |= _as_token_set(trip_style)
    # Normalise a couple of common multi-word tokens to their roots for matching.
    return {t.replace("_", " ") for t in kw if t}


def _score_item_for_trip(
    item: dict[str, Any],
    *,
    avg_high: float,
    rainy: bool,
    trip_keywords: set[str],
) -> float:
    """Heuristic 0..~10 relevance score; higher = more trip-appropriate."""
    score = 1.0  # baseline so every item stays eligible
    seasons = _as_token_set(item.get("season"))
    is_all_season = bool(seasons & _ALL_SEASON) or not seasons

    # Weather/season fit — the dominant signal for travel.
    if avg_high >= 26:
        if seasons & _WARM_SEASONS:
            score += 3.0
        if seasons & _COLD_SEASONS:
            score -= 2.5
    elif avg_high <= 12:
        if seasons & _COLD_SEASONS:
            score += 3.0
        if seasons & _WARM_SEASONS:
            score -= 2.5
    if is_all_season:
        score += 1.0  # versatile pieces are always good travel candidates

    # Activity / purpose / style fit — match against occasions, name, notes.
    haystack = (
        _as_token_set(item.get("occasion"))
        | _as_token_set(item.get("occasions"))
        | _as_token_set(item.get("name"))
        | _as_token_set(item.get("notes"))
        | _as_token_set(item.get("tags"))
    )
    haystack_text = " ".join(haystack)
    for kw in trip_keywords:
        if not kw:
            continue
        if kw in haystack:
            score += 1.5
        elif kw in haystack_text:  # substring (e.g. "beach" in "beachwear")
            score += 0.75

    # Rain: nudge waterproof/outer pieces up a touch.
    if rainy:
        cat = _normalise_category(str(item.get("category", "")))
        if cat == "outerwear" or "waterproof" in haystack_text or "rain" in haystack_text:
            score += 1.0

    return score


def _rank_closet_for_trip(
    closet_items: list[dict[str, Any]],
    weather_summary: dict[str, Any],
    activities: list[dict[str, Any]],
    purpose: str,
    trip_style: str | None,
    bag: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Return the most trip-relevant subset of the closet, preserving per-category
    coverage. Small closets pass through untouched.
    """
    if len(closet_items) <= _RANK_TRIM_THRESHOLD:
        return closet_items

    avg_high = float(weather_summary.get("avg_high", 20) or 20)
    rainy = bool(weather_summary.get("rainy_days", 0))
    trip_keywords = _trip_keywords(activities, purpose, trip_style)

    # Per-category candidate caps: give the model ~2x the bag limit so it has
    # real choice, with a sensible floor for categories the bag doesn't cap.
    cap_for: dict[str, int] = {
        "tops": max(6, int(bag.get("max_tops", 5)) * 2),
        "bottoms": max(4, int(bag.get("max_bottoms", 3)) * 2),
        "shoes": max(3, int(bag.get("max_shoes", 2)) * 2),
        "outerwear": max(2, int(bag.get("max_outerwear", 1)) * 2),
        "accessories": max(4, int(bag.get("max_accessories", 3)) * 2),
    }
    default_cap = 4

    scored_by_cat: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
    for item in closet_items:
        cat = _normalise_category(str(item.get("category", "")))
        s = _score_item_for_trip(item, avg_high=avg_high, rainy=rainy, trip_keywords=trip_keywords)
        scored_by_cat[cat].append((s, item))

    ranked: list[dict[str, Any]] = []
    for cat, scored in scored_by_cat.items():
        scored.sort(key=lambda t: t[0], reverse=True)
        ranked.extend(item for _, item in scored[: cap_for.get(cat, default_cap)])
    return ranked


# ── Closet grounding (anti-hallucination) ──────────────────────────────────────


def _norm_name(name: Any) -> str:
    """
    Normalise an item name for matching: lowercase alphanumerics only, so
    "Levi's 501 Jeans", "levis 501 jeans" and "Levi's  501-Jeans" all compare
    equal. Used only for closet-membership checks, never for display.
    """
    return "".join(c for c in str(name or "").lower() if c.isalnum())


def _closet_lookup_maps(
    closet_items: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return (id → closet item, normalised name → id) maps."""
    by_id: dict[str, dict[str, Any]] = {str(it["id"]): it for it in closet_items if it.get("id")}
    name_to_id: dict[str, str] = {
        _norm_name(it.get("name")): str(it["id"]) for it in closet_items if it.get("id") and it.get("name")
    }
    name_to_id.pop("", None)
    return by_id, name_to_id


def _ground_day_plans_to_closet(
    day_plans: list[dict[str, Any]],
    closet_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Verify every outfit item the model tagged as ``from_closet`` actually exists.

    - A valid ``closet_item_id`` keeps its id, and its display name/category are
      back-filled from the real closet record so the model can never pair a real
      id with an invented name.
    - A wrong/blank id whose *name* matches a real closet item is repaired by
      back-filling the real id.
    - An item that matches neither is downgraded to ``missing_recommended`` with
      its id cleared, so the UI never presents an invented item as owned.

    Returns the (mutated) day_plans and a count of corrected items.
    """
    by_id, name_to_id = _closet_lookup_maps(closet_items)

    corrected = 0
    for day in day_plans:
        for outfit in day.get("outfits", []):
            for item in outfit.get("items", []):
                source = str(item.get("source") or "").lower()
                cid = str(item.get("closet_item_id") or "").strip()
                name = _norm_name(item.get("item_name"))
                claims_closet = source == "from_closet" or bool(cid)
                if not claims_closet:
                    continue
                if cid and cid in by_id:
                    item["source"] = "from_closet"
                    # Real id, but the name/category must come from the closet
                    # record — never trust the model's rendering of an owned item.
                    real = by_id[cid]
                    real_name = str(real.get("name") or "")
                    if real_name and name != _norm_name(real_name):
                        item["item_name"] = real_name
                        corrected += 1
                    real_cat = real.get("category")
                    if real_cat:
                        item["category"] = _normalise_category(str(real_cat))
                    continue
                # id is wrong/blank — try to recover via a normalised name match.
                if name in name_to_id:
                    item["closet_item_id"] = name_to_id[name]
                    item["source"] = "from_closet"
                    corrected += 1
                    continue
                # Genuinely not in the closet — stop presenting it as owned.
                item["closet_item_id"] = None
                item["source"] = "missing_recommended"
                corrected += 1
    return day_plans, corrected


def _ground_rewear_strategy(
    rewear_strategy: list[dict[str, Any]],
    closet_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Ground rewear-strategy entries the same way as day plans: back-fill real
    ids/names where recoverable and DROP entries that reference items the user
    does not own — a rewear plan for a non-existent item is pure hallucination.

    Returns (grounded entries, count dropped/corrected).
    """
    by_id, name_to_id = _closet_lookup_maps(closet_items)
    grounded: list[dict[str, Any]] = []
    corrected = 0
    for entry in rewear_strategy:
        if not isinstance(entry, dict):
            corrected += 1
            continue
        cid = str(entry.get("closet_item_id") or "").strip()
        name = _norm_name(entry.get("item_name"))
        if cid and cid in by_id:
            real_name = str(by_id[cid].get("name") or "")
            if real_name and name != _norm_name(real_name):
                entry["item_name"] = real_name
                corrected += 1
            grounded.append(entry)
        elif name in name_to_id:
            entry["closet_item_id"] = name_to_id[name]
            corrected += 1
            grounded.append(entry)
        else:
            corrected += 1  # invented item — drop the whole entry
    return grounded, corrected


def _filter_owned_from_missing(
    missing_items: list[dict[str, Any]],
    closet_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Drop "missing" recommendations the user demonstrably already owns (inverse
    hallucination: telling the user to buy an item that is in their closet).
    """
    owned_names = {_norm_name(it.get("name")) for it in closet_items if it.get("name")}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for mi in missing_items:
        if not isinstance(mi, dict):
            dropped += 1
            continue
        name = _norm_name(mi.get("item_name") or mi.get("name"))
        if name and name in owned_names:
            dropped += 1
        else:
            kept.append(mi)
    return kept, dropped


def _compute_bag_capacity_summary(
    day_plans: list[dict[str, Any]],
    bag: dict[str, Any],
    ai_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Deterministic bag-capacity summary computed from the grounded day plans —
    replaces the LLM's self-reported packing_status/total_unique_items (which it
    routinely gets wrong) while keeping its free-text optimization_notes.
    """
    unique_by_cat: dict[str, set[str]] = defaultdict(set)
    for day in day_plans:
        for outfit in day.get("outfits", []):
            for item in outfit.get("items", []):
                name = str(item.get("item_name") or "")
                if not name:
                    continue
                cat = _normalise_category(str(item.get("category") or "general"))
                key = str(item.get("closet_item_id") or "") or _norm_name(name)
                unique_by_cat[cat].add(key)

    total_unique = sum(len(v) for v in unique_by_cat.values())
    status = "fits"
    for cat in ("tops", "bottoms", "shoes", "outerwear", "accessories"):
        limit = int(bag.get(f"max_{cat}", 0) or 0)
        count = len(unique_by_cat.get(cat, set()))
        if not limit:
            continue
        if count > limit:
            status = "overpacked"
            break
        if count == limit:
            status = "tight"

    notes = []
    if isinstance(ai_summary, dict):
        raw_notes = ai_summary.get("optimization_notes")
        if isinstance(raw_notes, list):
            notes = [str(n) for n in raw_notes if n]
    return {
        "packing_status": status,
        "total_unique_items": total_unique,
        "items_per_category": {cat: len(keys) for cat, keys in unique_by_cat.items()},
        "optimization_notes": notes,
    }


# ── AI packing prompt (activity-aware) ────────────────────────────────────────

# The rich planner enumerates at most this many days of detailed outfits. Longer
# trips get a "rotate the capsule" note instead of a per-day plan — this bounds
# the response size (and matches the 14-day caps in the weather table and the
# rule-based fallback). Without a bound, a 3-week trip asks the model for ~30 days
# of JSON, overflows the token ceiling, and truncates into unparseable output.
_MAX_PLANNED_DAYS = 14

# Completion-token budget for the rich call. A day-by-day planner's JSON grows
# roughly linearly with the number of days; a fixed 4k ceiling silently truncated
# long trips (→ json.loads fails → invisible rule-based fallback). We size the
# budget to the planned-day count instead, keeping the old 4k as a short-trip
# floor and capping below the model's hard output limit (gpt-4o = 16,384).
_PACKING_TOKENS_BASE = 1600
_PACKING_TOKENS_PER_DAY = 900
_PACKING_OUTPUT_TOKEN_CAP = 16000
_PACKING_TOKENS_FLOOR = 4000


def _packing_max_tokens(planned_days: int) -> int:
    """Scale the completion budget to the number of days being planned."""
    budget = _PACKING_TOKENS_BASE + _PACKING_TOKENS_PER_DAY * max(1, planned_days)
    return max(_PACKING_TOKENS_FLOOR, min(_PACKING_OUTPUT_TOKEN_CAP, budget))


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
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Core AI call — generates a full activity-aware day-by-day outfit planner.
    Returns parsed dict or None if AI unavailable.
    """
    if not settings.openai_api_key:
        return None

    bag = _get_bag_constraints(bag_size)
    # Bound the number of enumerated days so the JSON fits the token budget.
    planned_days = max(1, min(trip_days, _MAX_PLANNED_DAYS))
    weather_text = (
        f"{weather_summary.get('dominant_condition', 'Unknown')}, "
        f"avg high {weather_summary.get('avg_high', 22):.0f}°C / "
        f"low {weather_summary.get('avg_low', 15):.0f}°C, "
        f"{weather_summary.get('rainy_days', 0)} rainy day(s)"
    )
    per_day_block = _per_day_weather_table((weather_days or weather_summary.get("days", []))[:planned_days])
    if trip_days > planned_days:
        scope_note = (
            f"OUTPUT SCOPE: This trip is {trip_days} days. Produce detailed day_plans for the "
            f"FIRST {planned_days} days ONLY. In trip_summary.style_direction, tell the traveller "
            f"that days {planned_days + 1}–{trip_days} rotate and rewear the same capsule — do "
            f"NOT enumerate a separate plan for every day."
        )
    else:
        scope_note = f"OUTPUT SCOPE: Produce day_plans covering all {planned_days} day(s)."
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

    # Sanitise user-supplied trip fields before embedding in the prompt
    # (same treatment as the legacy prompt — injection here surfaces as
    # hallucinated/off-plan output downstream).
    safe_destination = sanitize_user_text(destination, field="notes", max_len=120)
    safe_purpose = sanitize_user_text(purpose, field="notes", max_len=80)
    safe_trip_style = sanitize_user_text(trip_style or "", field="notes", max_len=80)
    safe_notes = sanitize_user_text(notes or "", field="trip_notes") or "None"

    prompt = f"""You are FANI, a professional travel stylist and personal wardrobe manager. Generate a day-by-day travel outfit planner.

TRIP DETAILS:
- Destination: {safe_destination}
- Dates: {start_date} to {end_date} ({trip_days} days)
- Purpose: {safe_purpose}
- Trip style: {safe_trip_style or "not specified"}
- Bag size: {bag["label"]}
- Weather: {weather_text}
{per_day_block}
- Notes: {safe_notes}
{location_block}{style_block}
PLANNED ACTIVITIES:
{activities_block}

BAG SIZE CONSTRAINT: {bag["hint"]}

{scope_note}

USER'S CLOSET (ONLY use items from this list — never invent closet items):
{closet_text}

GROUNDING (STRICT): For every item with source "from_closet" you MUST copy the
exact "id" and exact "name" from the closet JSON above into closet_item_id and
item_name — character for character. Never invent, rename, or guess an id. If the
right item is not in the closet, use source "missing_recommended" with
closet_item_id null instead. An invented closet item is a hard failure.

MATCHING RULES: Match each outfit to the day's forecast (fabric weight and
coverage to the temperature, waterproof/outer layers on rainy days), the
activity's formality and footwear needs, and the user's style profile colours and
fit. Prefer cohesive colour pairings; do not pair clashing colours. Use each
item's "fit" field to balance silhouettes within an outfit — pair a
relaxed/oversized piece with a slim/fitted one rather than stacking volume on
volume; when fit is absent, judge proportion from the item name/category. Use each
item's "condition" field for dressy days: prefer new/excellent/good items for
formal or business activities, and avoid assigning "worn" or "fair" items to those
occasions when a better-condition option exists (condition does not matter for
casual/beach/gym days).

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
        decision = model_router.for_task(
            Task.PACKING_PLAN,
            max_tokens=_packing_max_tokens(planned_days),
            # Low temperature: outfit planning rewards consistent, grounded
            # choices over creative variety, and reduces id hallucination.
            temperature=0.3,
        )
        raw = await ai_service.chat(
            [{"role": "user", "content": prompt}],
            _PACKING_SYSTEM_PROMPT,
            use_json_mode=True,
            model=decision.model,
            max_tokens=decision.max_tokens,
            temperature=decision.temperature,
            telemetry=LLMTelemetry(
                operation=Task.PACKING_PLAN.value,
                user_id=user_id,
                tier=decision.tier.value,
                route_reasons=decision.reasons,
            ),
        )
        # Truncation used to be detected via finish_reason=length on the direct
        # client call. Through ai_service we only see the assembled text — bad
        # JSON (including truncated payloads) falls through to the rule-based plan.
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            logger.warning(
                "packing_ai_unparseable",
                destination=destination,
                trip_days=trip_days,
                planned_days=planned_days,
                max_tokens=decision.max_tokens,
                raw_chars=len(raw or ""),
            )
            return None
    except Exception as exc:
        logger.warning("ai_activity_packing_error", error=str(exc))
        return None


# ── Legacy sections derived from the grounded rich plan ──────────────────────
# take_from_your_closet / you_might_still_need used to come from a second LLM
# call, which doubled cost/latency and was an ungated hallucination surface.
# The grounded day plans already contain everything needed, so the legacy
# sections are now pure bookkeeping.


def _derive_legacy_sections(
    day_plans: list[dict[str, Any]],
    missing_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build take_from_your_closet / you_might_still_need from the (already
    grounded) rich plan. Every from_closet item is real by construction here,
    so no re-validation is needed.
    """
    take: dict[str, dict[str, Any]] = {}
    plan_missing: list[dict[str, Any]] = []
    for day in day_plans:
        day_label = f"Day {day.get('day_number', '?')}"
        for outfit in day.get("outfits", []):
            activity = str(outfit.get("activity") or "").strip()
            for item in outfit.get("items", []):
                name = str(item.get("item_name") or "").strip()
                if not name:
                    continue
                source = str(item.get("source") or "").lower()
                cid = str(item.get("closet_item_id") or "")
                if source == "from_closet" and cid:
                    entry = take.setdefault(
                        cid,
                        {
                            "item_id": cid,
                            "name": name,
                            "category": _normalise_category(str(item.get("category") or "general")),
                            "reason": f"Planned for {activity}" if activity else "Planned in your day-by-day outfits.",
                            "recommended_days": [],
                        },
                    )
                    if day_label not in entry["recommended_days"]:
                        entry["recommended_days"].append(day_label)
                elif source == "missing_recommended":
                    plan_missing.append(
                        {
                            "name": name,
                            "category": str(item.get("category") or "").lower() or "general",
                            "reason": f"Needed for {activity}" if activity else "Recommended for this trip.",
                        }
                    )

    still_need: list[dict[str, Any]] = []
    seen_need: set[str] = set()
    for entry in list(missing_items) + plan_missing:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("item_name") or entry.get("name") or "").strip()
        key = _norm_name(name)
        if not name or key in seen_need:
            continue
        still_need.append(
            {
                "name": name,
                "category": str(entry.get("category") or "").lower() or "general",
                "reason": str(entry.get("reason") or "Consider bringing this."),
            }
        )
        seen_need.add(key)
    return list(take.values()), still_need


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
    essentials: list[dict[str, Any]] = [
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
    user_id: str | None = None,
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

        # ── Rank closet by trip-relevance before prompting ────────────────────
        # Trims a large wardrobe to the items that actually fit this trip's
        # weather/activities/style so the model chooses from sharper candidates.
        # Grounding/validation below always runs against the FULL closet, so
        # trimming can never cause a real item to be flagged as hallucinated.
        bag = _get_bag_constraints(bag_size)
        ranked_closet = _rank_closet_for_trip(closet_items, weather_summary, activities, purpose, trip_style, bag)
        if len(ranked_closet) < len(closet_items):
            logger.info(
                "packing_closet_ranked",
                destination=destination,
                total=len(closet_items),
                selected=len(ranked_closet),
            )

        # ── Single activity-aware AI call ─────────────────────────────────────
        # The legacy take_from/you_might_need sections are derived from this
        # plan deterministically below — no second LLM call.
        ai_rich = await _ai_activity_aware_packing(
            destination,
            start_date,
            end_date,
            purpose,
            trip_style,
            bag_size,
            trip_days,
            ranked_closet,
            weather_summary,
            weather_days,
            activities,
            notes,
            style_profile_context_text=merged_ctx,
            rag_context=rag_context,
            location_context=location_context,
            user_id=user_id,
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

            # Ground every "from_closet" pick against the FULL closet: repair
            # recoverable ids/names and downgrade invented items to
            # missing_recommended. Rewear entries and "missing" recommendations
            # get the same treatment — every LLM field the UI renders as a fact
            # about the user's closet must survive a closet check.
            day_plans_rich, corrected = _ground_day_plans_to_closet(day_plans_rich, closet_items)
            rewear_strategy, rewear_corrected = _ground_rewear_strategy(rewear_strategy, closet_items)
            missing_items_rich, owned_dropped = _filter_owned_from_missing(missing_items_rich, closet_items)
            if corrected or rewear_corrected or owned_dropped:
                logger.info(
                    "packing_grounding_corrections",
                    destination=destination,
                    corrected=corrected,
                    rewear_corrected=rewear_corrected,
                    owned_dropped_from_missing=owned_dropped,
                )

            # Bag capacity is computed, not self-reported: the model's own
            # packing_status/total_unique_items are frequently wrong.
            bag_capacity_summary = _compute_bag_capacity_summary(day_plans_rich, bag, bag_capacity_summary)

            # Enrich with closet images (after grounding back-fills real ids)
            day_plans_rich = _enrich_day_plans_with_images(day_plans_rich, closet_items)
        else:
            # Fallback rule-based rich plans
            day_plans_rich = _rule_based_day_plans(closet_items, activities, start_date, trip_days, weather_days)

        # ── Legacy sections: derived from the grounded plan, no LLM ─────────
        if ai_rich:
            take_from_closet, still_need = _derive_legacy_sections(day_plans_rich, missing_items_rich)
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
