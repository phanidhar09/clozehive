"""Static festival calendar — Phase 0 of the web-intelligence roadmap.

Provides *dress-relevant* festival awareness with ZERO external API calls. A
curated, hand-maintained dataset maps festivals to the occasion + dress guidance
FANI needs to style for them, plus a lightweight country inference so a free-text
location ("Jaipur, India") or trip destination resolves to the right festivals.

This is the deterministic baseline. Later roadmap phases layer Tavily live search
on top for regional/movable festivals this table misses — but the big,
date-predictable ones (Diwali, Eid, Christmas, CNY, …) are covered here for free.

Design mirrors ``travel/services/location_intel_service``: curated data in,
prompt-ready / structured context out, graceful "" / None when nothing matches.

NOTE ON MOVABLE DATES: lunar/solar feast dates (Diwali, Eid, Holi, CNY, Easter …)
shift each year and are hard-coded per year below. They are accurate for the years
listed and should be extended yearly — or, from Phase 3, sourced live via Tavily.
Fixed-date festivals (Christmas, New Year, Valentine's …) are generated for every
year in ``_YEARS`` so they never need manual renewal within that window.
"""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict

# Years for which fixed-date festivals are auto-generated. Extend as needed.
_YEARS = (2026, 2027)

# How wide a window (days) counts as "around" a festival for nudges/lookahead.
FESTIVAL_LOOKAHEAD_DAYS = 4


class Festival(TypedDict):
    name: str
    emoji: str
    occasion: str  # feeds the OOTD/outfit occasion query — keep it stylable
    dress: str  # one-line dress guidance, prompt-ready
    scope: Any  # "global" or a tuple of country keys


# ─────────────────────────────────────────────────────────────────────────────
# Curated dress-relevant festival set
# ─────────────────────────────────────────────────────────────────────────────
# Each entry is the festival's *meta*; concrete dated occurrences are built below.

# Fixed-date festivals — (month, day, meta). Generated for every year in _YEARS.
_FIXED: list[tuple[int, int, Festival]] = [
    (
        1,
        1,
        {
            "name": "New Year's Day",
            "emoji": "🎉",
            "occasion": "celebratory party",
            "dress": "dressy, celebratory — a little sparkle or your sharpest going-out look.",
            "scope": "global",
        },
    ),
    (
        2,
        14,
        {
            "name": "Valentine's Day",
            "emoji": "❤️",
            "occasion": "romantic date",
            "dress": "elegant date-night look; reds, pinks or a refined monochrome.",
            "scope": "global",
        },
    ),
    (
        7,
        4,
        {
            "name": "Independence Day",
            "emoji": "🎆",
            "occasion": "casual patriotic",
            "dress": "relaxed, breathable summer casual; red/white/blue accents fit the day.",
            "scope": ("usa",),
        },
    ),
    (
        10,
        31,
        {
            "name": "Halloween",
            "emoji": "🎃",
            "occasion": "costume party",
            "dress": "playful — a costume or a dark, moody themed outfit.",
            "scope": "global",
        },
    ),
    (
        12,
        25,
        {
            "name": "Christmas",
            "emoji": "🎄",
            "occasion": "festive holiday gathering",
            "dress": "cozy-festive; reds, greens, gold accents, smart-casual for gatherings.",
            "scope": "global",
        },
    ),
    (
        12,
        31,
        {
            "name": "New Year's Eve",
            "emoji": "🥂",
            "occasion": "party celebration",
            "dress": "glamorous party wear — sequins, metallics, your boldest going-out fit.",
            "scope": "global",
        },
    ),
]

# Movable / year-specific festivals — explicit dates per year.
# Accurate for the years given; approximate where noted. Superseded by Tavily later.
_MOVABLE: list[tuple[date, Festival]] = [
    # ── 2026 ──
    (
        date(2026, 2, 17),
        {
            "name": "Chinese New Year",
            "emoji": "🧧",
            "occasion": "festive red celebration",
            "dress": "new clothes in red and gold; avoid black and white.",
            "scope": ("china", "singapore", "malaysia", "taiwan", "hong kong"),
        },
    ),
    (
        date(2026, 3, 4),
        {
            "name": "Holi",
            "emoji": "🎨",
            "occasion": "playful colour festival",
            "dress": "old white or expendable clothes you don't mind staining with colour.",
            "scope": ("india", "nepal"),
        },
    ),
    (
        date(2026, 3, 20),
        {  # approximate (lunar)
            "name": "Eid al-Fitr",
            "emoji": "🌙",
            "occasion": "festive traditional celebration",
            "dress": "your finest new traditional wear; modest, elegant, celebratory.",
            "scope": ("uae", "saudi arabia", "india", "pakistan", "indonesia", "malaysia", "egypt", "turkey"),
        },
    ),
    (
        date(2026, 4, 5),
        {
            "name": "Easter",
            "emoji": "🐣",
            "occasion": "spring smart-casual",
            "dress": "fresh spring pastels; smart-casual, church-appropriate if attending.",
            "scope": "global",
        },
    ),
    (
        date(2026, 5, 27),
        {  # approximate (lunar)
            "name": "Eid al-Adha",
            "emoji": "🌙",
            "occasion": "festive traditional celebration",
            "dress": "fine traditional attire; modest and celebratory.",
            "scope": ("uae", "saudi arabia", "india", "pakistan", "indonesia", "malaysia", "egypt", "turkey"),
        },
    ),
    (
        date(2026, 8, 28),
        {  # approximate
            "name": "Raksha Bandhan",
            "emoji": "🪢",
            "occasion": "ethnic family gathering",
            "dress": "traditional ethnic wear for a family celebration.",
            "scope": ("india",),
        },
    ),
    (
        date(2026, 9, 14),
        {  # approximate
            "name": "Ganesh Chaturthi",
            "emoji": "🐘",
            "occasion": "festive ethnic",
            "dress": "bright traditional wear; often kurta/saree in festive colours.",
            "scope": ("india",),
        },
    ),
    (
        date(2026, 10, 11),
        {  # Navratri begins (approx); spans ~9 nights
            "name": "Navratri",
            "emoji": "💃",
            "occasion": "festive garba night",
            "dress": "vibrant chaniya choli / kurta; bold colours and mirror-work for garba.",
            "scope": ("india",),
        },
    ),
    (
        date(2026, 10, 20),
        {  # approximate
            "name": "Dussehra",
            "emoji": "🏹",
            "occasion": "festive ethnic",
            "dress": "traditional festive attire in rich colours.",
            "scope": ("india",),
        },
    ),
    (
        date(2026, 11, 8),
        {
            "name": "Diwali",
            "emoji": "🪔",
            "occasion": "festive ethnic celebration",
            "dress": "traditional ethnic wear in jewel tones; embellished fabrics, gold accents.",
            "scope": ("india", "nepal", "singapore", "malaysia"),
        },
    ),
    (
        date(2026, 11, 26),
        {
            "name": "Thanksgiving",
            "emoji": "🦃",
            "occasion": "smart-casual family gathering",
            "dress": "comfortable smart-casual for a family meal; warm autumn tones.",
            "scope": ("usa",),
        },
    ),
    # ── 2027 (high-confidence subset; extend yearly) ──
    (
        date(2027, 2, 6),
        {
            "name": "Chinese New Year",
            "emoji": "🧧",
            "occasion": "festive red celebration",
            "dress": "new clothes in red and gold; avoid black and white.",
            "scope": ("china", "singapore", "malaysia", "taiwan", "hong kong"),
        },
    ),
    (
        date(2027, 3, 22),
        {
            "name": "Holi",
            "emoji": "🎨",
            "occasion": "playful colour festival",
            "dress": "old white or expendable clothes you don't mind staining with colour.",
            "scope": ("india", "nepal"),
        },
    ),
    (
        date(2027, 11, 5),
        {  # approximate
            "name": "Diwali",
            "emoji": "🪔",
            "occasion": "festive ethnic celebration",
            "dress": "traditional ethnic wear in jewel tones; embellished fabrics, gold accents.",
            "scope": ("india", "nepal", "singapore", "malaysia"),
        },
    ),
]


def _all_occurrences() -> list[tuple[date, Festival]]:
    """Flatten fixed + movable festivals into concrete (date, meta) occurrences."""
    out: list[tuple[date, Festival]] = []
    for month, day, meta in _FIXED:
        for year in _YEARS:
            try:
                out.append((date(year, month, day), meta))
            except ValueError:  # pragma: no cover — guards bad month/day
                continue
    out.extend(_MOVABLE)
    return out


_OCCURRENCES = _all_occurrences()


# ─────────────────────────────────────────────────────────────────────────────
# Country inference (free-text location/destination → country key)
# ─────────────────────────────────────────────────────────────────────────────

# Country names / aliases that may appear directly in a location string.
_COUNTRY_ALIASES: dict[str, str] = {
    "india": "india",
    "bharat": "india",
    "nepal": "nepal",
    "usa": "usa",
    "united states": "usa",
    "u.s.": "usa",
    "u.s.a": "usa",
    "america": "usa",
    "uk": "uk",
    "united kingdom": "uk",
    "england": "uk",
    "britain": "uk",
    "china": "china",
    "prc": "china",
    "hong kong": "hong kong",
    "taiwan": "taiwan",
    "singapore": "singapore",
    "malaysia": "malaysia",
    "indonesia": "indonesia",
    "uae": "uae",
    "united arab emirates": "uae",
    "emirates": "uae",
    "saudi arabia": "saudi arabia",
    "ksa": "saudi arabia",
    "pakistan": "pakistan",
    "egypt": "egypt",
    "turkey": "turkey",
    "türkiye": "turkey",
    "japan": "japan",
}

# Major cities → country, for when the string carries only a city name.
_CITY_COUNTRY: dict[str, str] = {
    "mumbai": "india",
    "delhi": "india",
    "new delhi": "india",
    "jaipur": "india",
    "bangalore": "india",
    "bengaluru": "india",
    "chennai": "india",
    "kolkata": "india",
    "hyderabad": "india",
    "pune": "india",
    "ahmedabad": "india",
    "goa": "india",
    "new york": "usa",
    "los angeles": "usa",
    "san francisco": "usa",
    "chicago": "usa",
    "boston": "usa",
    "seattle": "usa",
    "austin": "usa",
    "miami": "usa",
    "london": "uk",
    "manchester": "uk",
    "edinburgh": "uk",
    "dubai": "uae",
    "abu dhabi": "uae",
    "beijing": "china",
    "shanghai": "china",
    "shenzhen": "china",
    "guangzhou": "china",
    "singapore": "singapore",
    "kuala lumpur": "malaysia",
    "jakarta": "indonesia",
    "bali": "indonesia",
    "tokyo": "japan",
    "osaka": "japan",
    "kyoto": "japan",
    "istanbul": "turkey",
    "cairo": "egypt",
    "karachi": "pakistan",
    "lahore": "pakistan",
    "islamabad": "pakistan",
    "kathmandu": "nepal",
    "riyadh": "saudi arabia",
    "jeddah": "saudi arabia",
}


def infer_country(location: str | None) -> str | None:
    """Best-effort country key from a free-text location or destination string.

    Checks explicit country names/aliases first, then a major-city lookup.
    Returns None when nothing matches (global festivals still apply downstream).
    """
    if not location:
        return None
    text = location.strip().lower()
    if not text:
        return None

    # 1. Direct country mention anywhere in the string.
    for alias, country in _COUNTRY_ALIASES.items():
        if alias in text:
            return country

    # 2. City lookup — exact, then substring on the leading token.
    if text in _CITY_COUNTRY:
        return _CITY_COUNTRY[text]
    head = text.split(",")[0].strip()
    if head in _CITY_COUNTRY:
        return _CITY_COUNTRY[head]
    for city, country in _CITY_COUNTRY.items():
        if city in text:
            return country

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Lookups
# ─────────────────────────────────────────────────────────────────────────────


def _matches_country(festival: Festival, country: str | None) -> bool:
    """Global festivals match everyone; scoped ones need a country in scope."""
    scope = festival["scope"]
    if scope == "global":
        return True
    if country is None:
        return False
    return country in scope


def festivals_on(country: str | None, target: date) -> list[Festival]:
    """Festivals celebrated on ``target`` for the given country (+ global)."""
    return [meta for occ_date, meta in _OCCURRENCES if occ_date == target and _matches_country(meta, country)]


def festivals_in_range(country: str | None, start: date, end: date) -> list[tuple[date, Festival]]:
    """(date, festival) pairs falling within [start, end] inclusive, sorted."""
    hits = [
        (occ_date, meta)
        for occ_date, meta in _OCCURRENCES
        if start <= occ_date <= end and _matches_country(meta, country)
    ]
    return sorted(hits, key=lambda pair: pair[0])


def next_festival(
    country: str | None, today: date, within_days: int = FESTIVAL_LOOKAHEAD_DAYS
) -> tuple[date, Festival] | None:
    """The soonest festival within ``within_days`` of today, or None."""
    upcoming = festivals_in_range(country, today, date.fromordinal(today.toordinal() + within_days))
    return upcoming[0] if upcoming else None


# ─────────────────────────────────────────────────────────────────────────────
# Prompt / payload helpers
# ─────────────────────────────────────────────────────────────────────────────


def festival_occasion(festival: Festival) -> str:
    """The occasion label to drive OOTD closet retrieval + outfit generation."""
    return festival["occasion"]


def build_festival_context_block(festival: Festival, when: str = "today") -> str:
    """Prompt-ready festival block for outfit generation. "" if no festival."""
    if not festival:
        return ""
    return (
        "[FESTIVAL CONTEXT]\n"
        f"Festival: {festival['name']} {festival['emoji']} ({when})\n"
        f"Occasion: {festival['occasion']}\n"
        f"Dress guidance: {festival['dress']}\n"
        "Treat this as the occasion to dress for: prefer closet items that suit the "
        "festival's dress guidance, and reflect the celebratory intent in styling tips.\n"
        "[END FESTIVAL CONTEXT]"
    )
