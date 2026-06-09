"""Weather tool — live OpenWeather forecasts with a climate-profile fallback.

When ``OPENWEATHER_API_KEY`` is configured, ``get_weather_forecast`` /
``get_weather_summary`` return real day-by-day forecasts from the OpenWeather
5-day/3-hour API. The static climate profiles below are used only when:

* no API key is configured,
* the requested dates fall outside the ~5-day live window, or
* the upstream call fails for any reason.

Each ``WeatherDay`` carries a ``data_source`` ("live" or "static_profile") so the
agent — and downstream packing/outfit advice — can tell real forecasts apart
from climatology estimates.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import structlog
from langchain_core.tools import tool

from app.core.config import get_settings
from app.tools.schemas import WeatherDay, WeatherSummary

logger = structlog.get_logger("ai_agent.tools.weather")
settings = get_settings()

_OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
# OpenWeather's free 5-day/3-hour forecast reaches ~5 days out.
_FORECAST_WINDOW_DAYS = 5

# ── Climate profiles (condition, temp_high, temp_low) — fallback only ─────────

_PROFILES: dict[str, tuple[str, float, float]] = {
    "dubai": ("Sunny", 38.0, 28.0),
    "bangkok": ("Humid", 34.0, 26.0),
    "mumbai": ("Humid", 32.0, 25.0),
    "singapore": ("Showers", 31.0, 24.0),
    "miami": ("Sunny", 30.0, 24.0),
    "cancun": ("Sunny", 33.0, 26.0),
    "bali": ("Partly Cloudy", 29.0, 23.0),
    "rio": ("Sunny", 28.0, 21.0),
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
    "new york": ("Partly Cloudy", 18.0, 10.0),
    "los angeles": ("Sunny", 26.0, 16.0),
    "san francisco": ("Foggy", 18.0, 11.0),
    "chicago": ("Windy", 14.0, 6.0),
    "toronto": ("Partly Cloudy", 16.0, 8.0),
    "vancouver": ("Rainy", 13.0, 7.0),
    "montreal": ("Snowy", 0.0, -8.0),
    "tokyo": ("Partly Cloudy", 20.0, 13.0),
    "seoul": ("Clear", 18.0, 9.0),
    "beijing": ("Hazy", 22.0, 12.0),
    "hong kong": ("Humid", 28.0, 22.0),
    "sydney": ("Sunny", 22.0, 15.0),
    "melbourne": ("Changeable", 17.0, 10.0),
    "auckland": ("Partly Cloudy", 19.0, 12.0),
    "cairo": ("Sunny", 35.0, 22.0),
    "cape town": ("Sunny", 24.0, 15.0),
    "nairobi": ("Partly Cloudy", 25.0, 14.0),
    "marrakech": ("Sunny", 30.0, 18.0),
    "delhi": ("Hazy", 36.0, 24.0),
    "hyderabad": ("Partly Cloudy", 33.0, 22.0),
    "bangalore": ("Partly Cloudy", 28.0, 18.0),
    "chennai": ("Humid", 33.0, 26.0),
    "kolkata": ("Humid", 32.0, 24.0),
}

_DEFAULT = ("Partly Cloudy", 20.0, 12.0)
_CONDITION_CYCLE = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Partly Cloudy", "Sunny", "Sunny"]
_RAINY = {"Rainy", "Showers", "Humid", "Thunderstorms", "Drizzle"}
_COLD  = {"Snowy", "Freezing"}


def _profile(destination: str) -> tuple[str, float, float]:
    key = destination.strip().lower()
    if key in _PROFILES:
        return _PROFILES[key]
    first_word = key.split()[0] if key.split() else key
    for k, v in _PROFILES.items():
        if first_word in k:
            return v
    return _DEFAULT


def _day_condition(base_condition: str, offset: int) -> str:
    cycle_pos = offset % len(_CONDITION_CYCLE)
    cycle_cond = _CONDITION_CYCLE[cycle_pos]
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


def _static_day(destination: str, offset: int, current: date) -> WeatherDay:
    """One day of climatology-based estimate for the given offset into the trip."""
    base_cond, base_high, base_low = _profile(destination)
    condition = _day_condition(base_cond, offset)
    variation = math.sin(offset * 0.7) * 2.0
    high = round(base_high + variation, 1)
    low = round(base_low + variation * 0.6, 1)
    return WeatherDay(
        date=current.isoformat(),
        condition=condition,
        temp_high=high,
        temp_low=low,
        description=_description(condition, high, low),
        data_source="static_profile",
    )


def _fetch_weather_static(destination: str, start_date: str, end_date: str) -> list[WeatherDay]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    return [
        _static_day(destination, i, start + timedelta(days=i))
        for i in range((end - start).days + 1)
    ]


async def _fetch_owm_daily(destination: str) -> dict[str, dict[str, Any]]:
    """Call OpenWeather and aggregate 3-hourly slots into per-day buckets."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _OWM_FORECAST_URL,
            params={
                "q": destination,
                "appid": settings.openweather_api_key,
                "units": "metric",
                "cnt": 40,
            },
        )
        resp.raise_for_status()
        forecast_data = resp.json()

    daily: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"highs": [], "lows": [], "conditions": []}
    )
    for item in forecast_data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"])
        day_key = dt.date().isoformat()
        main = item["main"]
        daily[day_key]["highs"].append(main.get("temp_max", main["temp"]))
        daily[day_key]["lows"].append(main.get("temp_min", main["temp"]))
        daily[day_key]["conditions"].append(item["weather"][0]["description"].title())
    return daily


async def _fetch_weather(destination: str, start_date: str, end_date: str) -> list[WeatherDay]:
    """
    Return per-day weather for the date range.

    Uses the OpenWeather 5-day/3-hour forecast for in-window days when a key is
    configured; out-of-window days and any failure fall back to static profiles.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if not settings.openweather_api_key:
        return _fetch_weather_static(destination, start_date, end_date)

    # Entirely beyond the live forecast window → no point calling the API.
    if start > date.today() + timedelta(days=_FORECAST_WINDOW_DAYS):
        return _fetch_weather_static(destination, start_date, end_date)

    try:
        daily = await _fetch_owm_daily(destination)
    except Exception as exc:
        logger.warning("weather_owm_failed", destination=destination, error=str(exc))
        return _fetch_weather_static(destination, start_date, end_date)

    days: list[WeatherDay] = []
    current = start
    while current <= end:
        day_key = current.isoformat()
        bucket = daily.get(day_key)
        if bucket and bucket["highs"]:
            condition = Counter(bucket["conditions"]).most_common(1)[0][0]
            high = round(max(bucket["highs"]), 1)
            low = round(min(bucket["lows"]), 1)
            days.append(WeatherDay(
                date=day_key,
                condition=condition,
                temp_high=high,
                temp_low=low,
                description=_description(condition, high, low),
                data_source="live",
            ))
        else:
            # Beyond the live window — fill from climatology.
            days.append(_static_day(destination, (current - start).days, current))
        current += timedelta(days=1)
    return days


def _summarise_weather(days: list[WeatherDay]) -> WeatherSummary:
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

    sources = {d.data_source for d in days}
    if sources == {"live"}:
        data_source = "live"
    elif "live" in sources:
        data_source = "partial"
    else:
        data_source = "static_profile"

    return WeatherSummary(
        dominant_condition=dominant,
        avg_high=avg_high,
        avg_low=avg_low,
        rainy_days=rainy,
        total_days=len(days),
        recommendation=rec,
        data_source=data_source,
        days=days,
    )


# ── LangChain tools ───────────────────────────────────────────────────────────

@tool
async def get_weather_forecast(destination: str, start_date: str, end_date: str) -> str:
    """
    Fetch a day-by-day weather forecast for a travel destination.

    Args:
        destination: City or country name (e.g. 'London', 'Dubai', 'New York').
        start_date:  Trip start date in YYYY-MM-DD format.
        end_date:    Trip end date in YYYY-MM-DD format.

    Returns:
        JSON array of WeatherDay objects: date, condition, temp_high, temp_low,
        description, data_source ("live" or "static_profile").
    """
    if not destination.strip():
        return json.dumps({"error": "destination cannot be empty"})
    if start_date > end_date:
        return json.dumps({"error": "start_date must be before end_date"})
    try:
        days = await _fetch_weather(destination, start_date, end_date)
        return json.dumps([d.model_dump() for d in days], indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
async def get_weather_summary(destination: str, start_date: str, end_date: str) -> str:
    """
    Fetch and summarise weather — dominant condition, avg temps, rainy days, recommendation.

    Args:
        destination: City or country name.
        start_date:  Trip start in YYYY-MM-DD format.
        end_date:    Trip end in YYYY-MM-DD format.

    Returns:
        JSON WeatherSummary with dominant_condition, avg_high, avg_low, rainy_days,
        recommendation, data_source, and a days[] list.
    """
    if not destination.strip():
        return json.dumps({"error": "destination cannot be empty"})
    try:
        days = await _fetch_weather(destination, start_date, end_date)
        summary = _summarise_weather(days)
        return summary.model_dump_json(indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
