"""Centralized RAG query construction for consistent, accurate embeddings.

Natural-language queries outperform bare key:value tags for text-embedding models.
All RAG paths should build queries through these helpers so retrieval stays aligned
across chat, outfit builder, packing, and the /api/v1/rag endpoints.
"""

from __future__ import annotations

import re
from typing import Any

# Occasion aliases → canonical occasion labels used in fashion KB / history
_OCCASION_ALIASES: dict[str, tuple[str, ...]] = {
    "business casual": ("business casual", "smart casual office", "office wear", "work outfit"),
    "business formal": ("business formal", "interview", "boardroom", "corporate", "suit"),
    "formal": ("formal", "black tie", "gala", "evening event", "cocktail"),
    "wedding": ("wedding", "bridal", "ceremony", "reception"),
    "smart casual": ("smart casual", "dinner date", "elevated casual"),
    "casual": ("casual", "weekend", "everyday", "relaxed"),
    "travel": ("travel", "trip", "vacation", "holiday", "packing"),
    "beach": ("beach", "resort", "tropical", "pool"),
}

_SEASON_ALIASES: dict[str, tuple[str, ...]] = {
    "summer": ("summer", "hot", "heat", "humid", "sunny"),
    "winter": ("winter", "cold", "snow", "freezing", "layer"),
    "spring": ("spring", "mild", "bloom"),
    "fall": ("fall", "autumn", "crisp"),
}

_WEATHER_ALIASES: dict[str, tuple[str, ...]] = {
    "rain": ("rain", "rainy", "wet", "storm", "drizzle", "waterproof"),
    "cold": ("cold", "chilly", "freezing", "layer", "thermal"),
    "hot": ("hot", "warm", "heat", "humid", "breathable"),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _match_alias(text: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
    norm = _normalize(text)
    for canonical, terms in aliases.items():
        for term in terms:
            if term in norm:
                return canonical
    return None


def infer_query_signals(query: str) -> dict[str, str | None]:
    """Extract occasion, season, and weather hints from natural language."""
    norm = _normalize(query)
    occasion = _match_alias(norm, _OCCASION_ALIASES)
    season = _match_alias(norm, _SEASON_ALIASES)
    weather = _match_alias(norm, _WEATHER_ALIASES)
    return {"occasion": occasion, "season": season, "weather": weather}


def build_closet_rag_query(
    message: str,
    *,
    occasion: str | None = None,
    mood: str = "",
    weather: str = "",
) -> str:
    """Build a semantically rich query for closet item vector search."""
    parts: list[str] = []
    msg = message.strip()
    if msg:
        parts.append(msg)
    if occasion:
        parts.append(f"Occasion: {occasion}")
    if mood:
        parts.append(f"Mood: {mood}")
    if weather:
        parts.append(f"Weather: {weather}")
    return ". ".join(parts) if parts else "wardrobe styling request"


def build_fashion_knowledge_query(
    query: str,
    *,
    occasion: str | None = None,
    weather: str = "",
    category: str | None = None,
) -> str:
    """Enrich a fashion KB search query with structured styling context."""
    base = query.strip()
    hints: list[str] = []
    if occasion:
        hints.append(f"occasion {occasion}")
    if weather:
        hints.append(f"weather {weather}")
    if category:
        hints.append(f"topic {category}")
    if not hints:
        inferred = infer_query_signals(base)
        for key in ("occasion", "season", "weather"):
            val = inferred.get(key)
            if val:
                hints.append(f"{key} {val}")
    if hints:
        return f"{base}. Styling context: {', '.join(hints)}."
    return base


def build_outfit_history_query(
    *,
    occasion: str | None = None,
    weather: str = "",
    message: str = "",
) -> str:
    """Build an outfit-history search query.

    When the user message is available and no explicit occasion was set, prefer
    the message — it carries richer intent than a generic occasion label.
    """
    if message.strip() and not occasion:
        return build_closet_rag_query(message, weather=weather)
    occ = occasion or "general styling"
    parts = [f"Occasion: {occ}"]
    if weather:
        parts.append(f"Weather: {weather}")
    if message.strip():
        parts.append(f"Request: {message.strip()[:300]}")
    return ". ".join(parts)


def build_packing_memory_query(
    destination: str,
    purpose: str,
    weather_summary: dict[str, Any] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Build a packing-memory search query."""
    parts = [f"Destination: {destination}", f"Purpose: {purpose}"]
    if start_date and end_date:
        parts.append(f"Dates: {start_date} to {end_date}")
    if weather_summary:
        cond = weather_summary.get("dominant_condition", "")
        avg_high = weather_summary.get("avg_high")
        avg_low = weather_summary.get("avg_low")
        rainy = weather_summary.get("rainy_days", 0)
        if cond:
            parts.append(f"Weather: {cond}")
        if avg_high is not None:
            parts.append(f"Average high {avg_high:.0f}°C")
        if avg_low is not None:
            parts.append(f"Average low {avg_low:.0f}°C")
        if rainy:
            parts.append(f"{rainy} rainy days")
    return ". ".join(parts)


def extract_keywords(query: str, *, max_keywords: int = 6) -> list[str]:
    """Extract meaningful tokens for keyword fallback search."""
    stop = {
        "a",
        "an",
        "the",
        "for",
        "and",
        "or",
        "to",
        "in",
        "on",
        "at",
        "of",
        "is",
        "it",
        "my",
        "me",
        "i",
        "what",
        "should",
        "wear",
        "outfit",
        "with",
        "from",
        "this",
        "that",
        "please",
        "help",
        "need",
        "want",
    }
    tokens = re.findall(r"[a-z0-9]+", _normalize(query))
    seen: set[str] = set()
    keywords: list[str] = []
    for tok in tokens:
        if len(tok) < 3 or tok in stop or tok in seen:
            continue
        seen.add(tok)
        keywords.append(tok)
        if len(keywords) >= max_keywords:
            break
    return keywords
