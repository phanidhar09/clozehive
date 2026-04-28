"""
Weather service — deterministic mock weather by destination.
No AI calls; fully offline. Used by packing and agent.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from shared.logger import get_logger
from shared.schemas import WeatherDay, WeatherSummary

logger = get_logger(__name__)

# ── Climate profiles ──────────────────────────────────────────────────────────

_CLIMATES: dict[str, dict[str, Any]] = {
    "dubai": {
        "conditions": ["sunny", "sunny", "sunny", "hazy"],
        "high": (30, 42),
        "low": (22, 32),
    },
    "london": {
        "conditions": ["cloudy", "rainy", "overcast", "partly cloudy"],
        "high": (8, 18),
        "low": (4, 12),
    },
    "paris": {
        "conditions": ["partly cloudy", "rainy", "sunny", "cloudy"],
        "high": (10, 22),
        "low": (5, 14),
    },
    "new york": {
        "conditions": ["sunny", "partly cloudy", "windy", "rainy"],
        "high": (5, 28),
        "low": (0, 20),
    },
    "mumbai": {
        "conditions": ["humid", "rainy", "cloudy", "sunny"],
        "high": (28, 36),
        "low": (22, 28),
    },
    "tokyo": {
        "conditions": ["sunny", "partly cloudy", "rainy", "windy"],
        "high": (10, 30),
        "low": (5, 22),
    },
    "sydney": {
        "conditions": ["sunny", "warm", "partly cloudy", "breezy"],
        "high": (18, 30),
        "low": (12, 22),
    },
    "bali": {
        "conditions": ["tropical", "humid", "partly cloudy", "rainy"],
        "high": (28, 34),
        "low": (22, 26),
    },
}

_DEFAULT_CLIMATE = {
    "conditions": ["partly cloudy", "sunny", "cloudy", "rainy"],
    "high": (15, 25),
    "low": (8, 18),
}

_CONDITION_DESCRIPTIONS = {
    "sunny": "Clear skies — perfect for light layers.",
    "rainy": "Rainfall expected — bring waterproofs.",
    "cloudy": "Overcast but dry.",
    "partly cloudy": "Mixed skies, comfortable.",
    "windy": "Breezy — a jacket recommended.",
    "overcast": "Grey skies, possible drizzle.",
    "humid": "High humidity, light breathable fabrics best.",
    "tropical": "Hot and tropical — lightweight clothing only.",
    "hazy": "Hazy sunshine — stay hydrated.",
    "warm": "Warm and pleasant.",
    "breezy": "Light breeze, comfortable temperatures.",
    "snowy": "Snow expected — full winter gear.",
}


def _get_climate(destination: str) -> dict[str, Any]:
    key = destination.lower().strip()
    for city, profile in _CLIMATES.items():
        if city in key or key in city:
            return profile
    return _DEFAULT_CLIMATE


def fetch_weather(destination: str, start_date: str, end_date: str) -> list[WeatherDay]:
    """Return day-by-day mock weather for the trip."""
    logger.info("Fetching weather for %s from %s to %s", destination, start_date, end_date)

    climate = _get_climate(destination)
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days: list[WeatherDay] = []

    current = start
    while current <= end:
        condition = random.choice(climate["conditions"])
        high = round(random.uniform(*climate["high"]), 1)
        low = round(random.uniform(*climate["low"]), 1)
        if low > high:
            low, high = high, low

        days.append(
            WeatherDay(
                date=current.isoformat(),
                condition=condition,
                temp_high=high,
                temp_low=low,
                description=_CONDITION_DESCRIPTIONS.get(condition, condition.capitalize() + "."),
            )
        )
        current += timedelta(days=1)

    logger.info("Generated %d weather days for %s", len(days), destination)
    return days


def summarise_weather(days: list[WeatherDay]) -> WeatherSummary:
    """Aggregate weather days into a summary struct."""
    if not days:
        return WeatherSummary(
            dominant_condition="unknown",
            avg_high=0,
            avg_low=0,
            rainy_days=0,
            recommendation="No weather data available.",
        )

    from collections import Counter

    conditions = [d.condition for d in days]
    dominant_condition = Counter(conditions).most_common(1)[0][0]
    avg_high = round(sum(d.temp_high for d in days) / len(days), 1)
    avg_low = round(sum(d.temp_low for d in days) / len(days), 1)
    rainy_days = sum(1 for d in days if "rain" in d.condition or "shower" in d.condition)

    # Build recommendation
    parts: list[str] = []
    if avg_high > 30:
        parts.append("Very hot — lightweight breathable fabrics essential.")
    elif avg_high > 20:
        parts.append("Warm — light layers and t-shirts ideal.")
    elif avg_high > 10:
        parts.append("Mild — a light jacket and layers recommended.")
    else:
        parts.append("Cold — warm coats, thermals, and boots needed.")

    if rainy_days > len(days) // 2:
        parts.append("Frequent rain — waterproof jacket and umbrella are must-haves.")
    elif rainy_days > 0:
        parts.append("Some rain expected — pack a light rain layer.")

    recommendation = " ".join(parts) if parts else "Comfortable conditions — standard packing applies."

    return WeatherSummary(
        dominant_condition=dominant_condition,
        avg_high=avg_high,
        avg_low=avg_low,
        rainy_days=rainy_days,
        recommendation=recommendation,
        days=days,
    )
