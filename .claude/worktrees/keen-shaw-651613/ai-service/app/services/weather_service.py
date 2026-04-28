"""
Mock weather service.
Returns plausible weather based on destination keywords + date range.
Swap fetch_weather() body for a real API call (OpenWeatherMap / WeatherAPI) when ready.
"""
import random
from datetime import date, timedelta
from app.models.schemas import WeatherDay

# Destination → rough climate profile
CLIMATE_MAP = {
    "dubai": {"condition_pool": ["sunny", "hot", "clear"], "temp_range": (30, 42)},
    "london": {"condition_pool": ["cloudy", "rainy", "overcast"], "temp_range": (8, 18)},
    "paris": {"condition_pool": ["partly_cloudy", "sunny", "light_rain"], "temp_range": (12, 22)},
    "new york": {"condition_pool": ["sunny", "windy", "cloudy", "snow"], "temp_range": (0, 20)},
    "mumbai": {"condition_pool": ["humid", "rainy", "hot"], "temp_range": (25, 35)},
    "tokyo": {"condition_pool": ["sunny", "partly_cloudy", "rainy"], "temp_range": (10, 28)},
    "sydney": {"condition_pool": ["sunny", "warm", "partly_cloudy"], "temp_range": (18, 28)},
    "bali": {"condition_pool": ["hot", "humid", "tropical_rain"], "temp_range": (26, 33)},
}

DEFAULT_CLIMATE = {"condition_pool": ["sunny", "partly_cloudy", "cloudy"], "temp_range": (18, 26)}

CONDITION_DESC = {
    "sunny": "Clear and sunny skies",
    "hot": "Hot and dry conditions",
    "clear": "Clear skies, good visibility",
    "cloudy": "Overcast and cloudy",
    "rainy": "Rain expected, carry an umbrella",
    "overcast": "Grey skies, mild conditions",
    "partly_cloudy": "Mix of sun and cloud",
    "light_rain": "Light showers possible",
    "windy": "Windy with gusts",
    "snow": "Snow expected, dress warmly",
    "humid": "Hot and humid",
    "tropical_rain": "Heavy tropical rain",
    "warm": "Warm and pleasant",
}


def fetch_weather(destination: str, start_date: str, end_date: str) -> list[WeatherDay]:
    key = destination.lower().strip()
    climate = DEFAULT_CLIMATE
    for city, profile in CLIMATE_MAP.items():
        if city in key:
            climate = profile
            break

    days: list[WeatherDay] = []
    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    while current <= end:
        condition = random.choice(climate["condition_pool"])
        t_low = random.uniform(*climate["temp_range"]) - 5
        t_high = t_low + random.uniform(4, 9)
        days.append(WeatherDay(
            date=current.isoformat(),
            condition=condition,
            temp_high=round(t_high, 1),
            temp_low=round(t_low, 1),
            description=CONDITION_DESC.get(condition, "Variable conditions"),
        ))
        current += timedelta(days=1)

    return days


def summarise_weather(days: list[WeatherDay]) -> dict:
    if not days:
        return {}
    temps_high = [d.temp_high for d in days]
    temps_low = [d.temp_low for d in days]
    conditions = [d.condition for d in days]
    dominant = max(set(conditions), key=conditions.count)
    rainy_days = sum(1 for c in conditions if "rain" in c or "snow" in c)
    return {
        "dominant_condition": dominant,
        "avg_high": round(sum(temps_high) / len(temps_high), 1),
        "avg_low": round(sum(temps_low) / len(temps_low), 1),
        "rainy_days": rainy_days,
        "total_days": len(days),
        "recommendation": _weather_recommendation(dominant, sum(temps_high) / len(temps_high), rainy_days),
    }


def _weather_recommendation(condition: str, avg_temp: float, rainy_days: int) -> str:
    parts = []
    if avg_temp > 30:
        parts.append("Pack light, breathable fabrics")
    elif avg_temp < 10:
        parts.append("Pack warm layers and a heavy jacket")
    else:
        parts.append("Pack versatile mid-weight clothing")
    if rainy_days > 0:
        parts.append(f"Expect rain on {rainy_days} day(s) — include a rain jacket or umbrella")
    return "; ".join(parts)
