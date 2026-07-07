"""Inline AI tools — weather, outfit, packing."""
from app.tools.weather import get_weather_forecast, get_weather_summary
from app.tools.outfit import generate_outfit_suggestions, get_outfit_style_tips
from app.tools.packing import get_packing_checklist

ALL_TOOLS = [
    get_weather_forecast,
    get_weather_summary,
    generate_outfit_suggestions,
    get_outfit_style_tips,
    get_packing_checklist,
]
