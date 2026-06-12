"""Consolidated weather service formerly provided by the weather MCP."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

settings = get_settings()

# ── Shared HTTP client (closed via close_client() at service shutdown) ───────

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=15)
    return _http


async def close_client() -> None:
    global _http
    if _http and not _http.is_closed:
        await _http.aclose()
    _http = None


_PROFILES: dict[str, tuple[str, float, float]] = {
    "dubai": ("Sunny", 38.0, 28.0),
    "bangkok": ("Humid", 34.0, 26.0),
    "mumbai": ("Humid", 32.0, 25.0),
    "singapore": ("Showers", 31.0, 24.0),
    "miami": ("Sunny", 30.0, 24.0),
    "bali": ("Partly Cloudy", 29.0, 23.0),
    "london": ("Cloudy", 15.0, 9.0),
    "paris": ("Partly Cloudy", 18.0, 10.0),
    "amsterdam": ("Rainy", 13.0, 7.0),
    "rome": ("Sunny", 22.0, 13.0),
    "new york": ("Partly Cloudy", 18.0, 10.0),
    "los angeles": ("Sunny", 26.0, 16.0),
    "san francisco": ("Foggy", 18.0, 11.0),
    "chicago": ("Windy", 14.0, 6.0),
    "tokyo": ("Partly Cloudy", 20.0, 13.0),
    "sydney": ("Sunny", 22.0, 15.0),
    "delhi": ("Hazy", 36.0, 24.0),
    "hyderabad": ("Partly Cloudy", 33.0, 22.0),
}
_DEFAULT = ("Partly Cloudy", 20.0, 12.0)
_CONDITION_CYCLE = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Partly Cloudy", "Sunny", "Sunny"]
_RAINY = {"Rainy", "Showers", "Humid", "Thunderstorms", "Drizzle"}


def _profile(destination: str) -> tuple[str, float, float]:
    key = destination.strip().lower()
    if key in _PROFILES:
        return _PROFILES[key]
    for profile_key, value in _PROFILES.items():
        if key.split()[0] in profile_key:
            return value
    return _DEFAULT


def _description(condition: str, high: float, low: float) -> str:
    return f"{condition}, high {high:.0f}°C / low {low:.0f}°C."


def fetch_weather(destination: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    base_cond, base_high, base_low = _profile(destination)
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = []
    for i in range((end - start).days + 1):
        current = start + timedelta(days=i)
        condition = base_cond if i % 3 == 0 else _CONDITION_CYCLE[i % len(_CONDITION_CYCLE)]
        variation = math.sin(i * 0.7) * 2.0
        high = round(base_high + variation, 1)
        low = round(base_low + variation * 0.6, 1)
        days.append(
            {
                "date": current.isoformat(),
                "condition": condition,
                "temp_high": high,
                "temp_low": low,
                "description": _description(condition, high, low),
                "data_source": "static_profile",
            }
        )
    return days


def summarise_weather(days: list[dict[str, Any]]) -> dict[str, Any]:
    dominant = Counter(day["condition"] for day in days).most_common(1)[0][0]
    avg_high = round(sum(float(day["temp_high"]) for day in days) / len(days), 1)
    avg_low = round(sum(float(day["temp_low"]) for day in days) / len(days), 1)
    rainy_days = sum(1 for day in days if day["condition"] in _RAINY)
    if rainy_days >= len(days) // 2:
        recommendation = "Pack waterproof layers and quick-dry fabrics."
    elif avg_high >= 30:
        recommendation = "Prioritise breathable fabrics and sun protection."
    elif avg_high <= 12:
        recommendation = "Bring warm layers and outerwear."
    else:
        recommendation = "Mild conditions; versatile layers should work well."
    # "live" if every day has live OWM data; "partial" if mixed; "static_profile" if all fallback
    sources = {day.get("data_source", "static_profile") for day in days}
    if sources == {"live"}:
        data_source = "live"
    elif "live" in sources:
        data_source = "partial"
    else:
        data_source = "static_profile"
    return {
        "dominant_condition": dominant,
        "avg_high": avg_high,
        "avg_low": avg_low,
        "rainy_days": rainy_days,
        "total_days": len(days),
        "recommendation": recommendation,
        "data_source": data_source,
        "days": days,
    }


async def fetch_weather_async(destination: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """
    Fetch per-day weather for a date range.
    Uses OWM 5-day/3-hour forecast when the API key is set and dates fall within range.
    Falls back to the static profile model for out-of-range or keyless requests.
    """
    if not settings.openweather_api_key:
        return fetch_weather(destination, start_date, end_date)

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    today = date.today()
    forecast_limit = today + timedelta(days=5)

    # For dates fully beyond the 5-day window, use static profiles
    if start > forecast_limit:
        return fetch_weather(destination, start_date, end_date)

    try:
        resp = await _client().get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": destination,
                "appid": settings.openweather_api_key,
                "units": "metric",
                "cnt": 40,
            },
        )
        resp.raise_for_status()
        forecast_data = resp.json()

        # Aggregate 3-hourly slots into daily summaries
        daily: dict[str, dict[str, Any]] = defaultdict(lambda: {"highs": [], "lows": [], "conditions": []})
        for item in forecast_data.get("list", []):
            dt = datetime.fromtimestamp(item["dt"])
            day_key = dt.date().isoformat()
            daily[day_key]["highs"].append(item["main"].get("temp_max", item["main"]["temp"]))
            daily[day_key]["lows"].append(item["main"].get("temp_min", item["main"]["temp"]))
            daily[day_key]["conditions"].append(item["weather"][0]["description"].title())

        result: list[dict[str, Any]] = []
        current = start
        while current <= end:
            day_key = current.isoformat()
            if day_key in daily:
                d = daily[day_key]
                condition = Counter(d["conditions"]).most_common(1)[0][0]
                high = round(max(d["highs"]), 1)
                low = round(min(d["lows"]), 1)
                source = "live"
            else:
                # Beyond forecast window — use static profile for remaining days
                base_cond, base_high, base_low = _profile(destination)
                i = (current - start).days
                condition = base_cond if i % 3 == 0 else _CONDITION_CYCLE[i % len(_CONDITION_CYCLE)]
                variation = math.sin(i * 0.7) * 2.0
                high = round(base_high + variation, 1)
                low = round(base_low + variation * 0.6, 1)
                source = "static_profile"
            result.append(
                {
                    "date": day_key,
                    "condition": condition,
                    "temp_high": high,
                    "temp_low": low,
                    "description": _description(condition, high, low),
                    "data_source": source,
                }
            )
            current += timedelta(days=1)

        return result

    except Exception:
        return fetch_weather(destination, start_date, end_date)


async def get_weather_by_city(city_name: str) -> dict[str, Any]:
    if settings.openweather_api_key:
        response = await _client().get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city_name, "appid": settings.openweather_api_key, "units": "metric"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        temp_c = float(data["main"]["temp"])
        return {
            "location_label": city_name,
            "condition": data["weather"][0]["description"].title(),
            "temp_c": round(temp_c, 1),
            "temp_f": round(temp_c * 9 / 5 + 32, 1),
            "feels_like_c": round(float(data["main"]["feels_like"]), 1),
            "humidity": int(data["main"]["humidity"]),
        }
    condition, high, low = _profile(city_name)
    temp_c = round((high + low) / 2, 1)
    return {
        "location_label": city_name,
        "condition": condition,
        "temp_c": temp_c,
        "temp_f": round(temp_c * 9 / 5 + 32, 1),
        "feels_like_c": temp_c,
        "humidity": 55,
    }


async def get_current_weather(lat: float, lon: float, location_label: str | None = None) -> dict[str, Any]:
    if settings.openweather_api_key:
        response = await _client().get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": settings.openweather_api_key, "units": "metric"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        temp_c = float(data["main"]["temp"])
        return {
            "location_label": location_label or data.get("name") or f"{lat:.2f},{lon:.2f}",
            "condition": data["weather"][0]["description"].title(),
            "temp_c": round(temp_c, 1),
            "temp_f": round(temp_c * 9 / 5 + 32, 1),
            "feels_like_c": round(float(data["main"]["feels_like"]), 1),
            "humidity": int(data["main"]["humidity"]),
        }
    return await get_weather_by_city(location_label or "San Francisco")
