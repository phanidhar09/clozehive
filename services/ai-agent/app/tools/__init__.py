"""Inline AI tools — weather, outfit, packing."""
from app.tools.weather import get_weather_forecast, get_weather_summary
from app.tools.outfit import generate_outfit_suggestions, get_outfit_style_tips
from app.tools.packing import generate_trip_packing_list, get_packing_checklist

ALL_TOOLS = [
    get_weather_forecast,
    get_weather_summary,
    generate_outfit_suggestions,
    get_outfit_style_tips,
    generate_trip_packing_list,
    get_packing_checklist,
]
