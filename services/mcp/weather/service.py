"""Weather service — climate-profile-based forecast generator."""

from __future__ import annotations

import math
from collections import Counter
from datetime import date, timedelta

from shared.schemas import WeatherDay, WeatherSummary

# ── Climate profiles (condition, temp_high, temp_low) ─────────────────────────

_PROFILES: dict[str, tuple[str, float, float]] = {
    # Tropical / hot
    "dubai": ("Sunny", 38.0, 28.0),
    "bangkok": ("Humid", 34.0, 26.0),
    "mumbai": ("Humid", 32.0, 25.0),
    "singapore": ("Showers", 31.0, 24.0),
    "miami": ("Sunny", 30.0, 24.0),
    "cancun": ("Sunny", 33.0, 26.0),
    "bali": ("Partly Cloudy", 29.0, 23.0),
    "rio": ("Sunny", 28.0, 21.0),

    # Temperate / European
    "london": ("Cloudy", 15.0, 9.0),
    "paris": ("Partly Cloudy", 18.0, 10.0),
    "amsterdam": ("Rainy", 13.0, 7.0),
    "berlin": ("Partly Cloudy", 16.0, 8.0),
    "rome": ("Sunny", 22.0, 13.0),
    "barcelona": ("Sunny", 24.0, 16.0),
    "madrid": ("Sunny", 26.0, 14.0),
    "lisbon": ("Sunny", 23.0, 14.0),
    "vienna": ("Partly Cloudy", 17.0, 9.0),
    "prague": ("Cloudy", 15.0, 7.0),
    "zurich": ("Rainy", 14.0, 6.0),

    # North America
    "new york": ("Partly Cloudy", 18.0, 10.0),
    "los angeles": ("Sunny", 26.0, 16.0),
    "san francisco": ("Foggy", 18.0, 11.0),
    "chicago": ("Windy", 14.0, 6.0),
    "toronto": ("Partly Cloudy", 16.0, 8.0),
    "vancouver": ("Rainy", 13.0, 7.0),
    "montreal": ("Snowy", 0.0, -8.0),

    # Asia-Pacific
    "tokyo": ("Partly Cloudy", 20.0, 13.0),
    "seoul": ("Clear", 18.0, 9.0),
    "beijing": ("Hazy", 22.0, 12.0),
    "hong kong": ("Humid", 28.0, 22.0),
    "sydney": ("Sunny", 22.0, 15.0),
    "melbourne": ("Changeable", 17.0, 10.0),
    "auckland": ("Partly Cloudy", 19.0, 12.0),

    # Middle East / Africa
    "cairo": ("Sunny", 35.0, 22.0),
    "cape town": ("Sunny", 24.0, 15.0),
    "nairobi": ("Partly Cloudy", 25.0, 14.0),
    "marrakech": ("Sunny", 30.0, 18.0),

    # India
    "delhi": ("Hazy", 36.0, 24.0),
    "hyderabad": ("Partly Cloudy", 33.0, 22.0),
    "bangalore": ("Partly Cloudy", 28.0, 18.0),
    "chennai": ("Humid", 33.0, 26.0),
    "kolkata": ("Humid", 32.0, 24.0),
}

_DEFAULT = ("Partly Cloudy", 20.0, 12.0)

_CONDITION_CYCLE = [
    "Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Partly Cloudy", "Sunny", "Sunny",
]

_RAINY = {"Rainy", "Showers", "Humid", "Thunderstorms", "Drizzle"}
_COLD  = {"Snowy", "Freezing"}


def _profile(destination: str) -> tuple[str, float, float]:
    key = destination.strip().lower()
    if key in _PROFILES:
        return _PROFILES[key]
    # fuzzy match on first word
    first_word = key.split()[0]
    for k, v in _PROFILES.items():
        if first_word in k:
            return v
    return _DEFAULT


def _day_condition(base_condition: str, offset: int) -> str:
    """Vary the condition slightly across days for realism."""
    cycle_pos = offset % len(_CONDITION_CYCLE)
    cycle_cond = _CONDITION_CYCLE[cycle_pos]

    # Blend: 60 % base, 40 % cycle
    if offset % 3 == 0:
        return base_condition
    return cycle_cond


def _description(condition: str, high: float, low: float) -> str:
    templates: dict[str, str] = {
        "Sunny": f"Clear skies with highs around {high:.0f}°C. Perfect outdoor weather.",
        "Partly Cloudy": f"Mix of sun and cloud, {high:.0f}°C/{low:.0f}°C. Light layers recommended.",
        "Cloudy": f"Overcast with highs of {high:.0f}°C. Bring a light jacket.",
        "Rainy": f"Expect rain, {high:.0f}°C/{low:.0f}°C. Pack a waterproof layer.",
        "Showers": f"Scattered showers, {high:.0f}°C/{low:.0f}°C. Umbrella advised.",
        "Humid": f"Hot and humid, {high:.0f}°C. Breathable fabrics essential.",
        "Snowy": f"Snow expected, {high:.0f}°C/{low:.0f}°C. Full winter gear required.",
        "Foggy": f"Foggy mornings clearing to {high:.0f}°C. Layering ideal.",
        "Windy": f"Breezy with gusts, {high:.0f}°C. Secure lightweight items.",
        "Hazy": f"Hazy skies, {high:.0f}°C/{low:.0f}°C. Sunglasses recommended.",
        "Changeable": f"Variable weather, {high:.0f}°C/{low:.0f}°C. Pack versatile pieces.",
        "Clear": f"Clear and pleasant, {high:.0f}°C/{low:.0f}°C. Light clothing suitable.",
    }
    return templates.get(condition, f"{condition}, high {high:.0f}°C / low {low:.0f}°C.")


def fetch_weather(destination: str, start_date: str, end_date: str) -> list[WeatherDay]:
    """Generate a realistic day-by-day forecast for a destination."""
    base_cond, base_high, base_low = _profile(destination)

    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    days: list[WeatherDay] = []

    for i in range((end - start).days + 1):
        current = start + timedelta(days=i)
        condition = _day_condition(base_cond, i)

        # ± small temp variation per day
        variation = math.sin(i * 0.7) * 2.0
        high = round(base_high + variation, 1)
        low  = round(base_low  + variation * 0.6, 1)

        days.append(WeatherDay(
            date=current.isoformat(),
            condition=condition,
            temp_high=high,
            temp_low=low,
            description=_description(condition, high, low),
        ))

    return days


def summarise_weather(days: list[WeatherDay]) -> WeatherSummary:
    """Collapse a day list into a concise trip summary."""
    conditions = [d.condition for d in days]
    dominant = Counter(conditions).most_common(1)[0][0]

    avg_high = round(sum(d.temp_high for d in days) / len(days), 1)
    avg_low  = round(sum(d.temp_low  for d in days) / len(days), 1)
    rainy    = sum(1 for d in days if d.condition in _RAINY)

    if dominant in _COLD:
        rec = "Heavy winter clothing required — wool, thermals, and a waterproof shell."
    elif dominant in _RAINY or rainy >= len(days) // 2:
        rec = "Pack a waterproof jacket and quick-dry fabrics for frequent rain."
    elif avg_high >= 30:
        rec = "Hot climate — prioritise lightweight, breathable, and moisture-wicking fabrics."
    elif avg_high <= 12:
        rec = "Cool weather — bring layers, a mid-layer fleece, and a warm jacket."
    else:
        rec = "Mild conditions — versatile layers covering both warm and cool periods."

    return WeatherSummary(
        dominant_condition=dominant,
        avg_high=avg_high,
        avg_low=avg_low,
        rainy_days=rainy,
        total_days=len(days),
        recommendation=rec,
        days=days,
    )
