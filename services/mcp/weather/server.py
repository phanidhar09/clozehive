"""
Weather MCP Server — port 8010
Production-grade: health endpoint, structured logging, input validation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from shared.config import get_settings
from shared.health import health_payload
from shared.logger import get_logger
from shared.schemas import WeatherDay, WeatherSummary
from service import fetch_weather, summarise_weather

logger = get_logger("weather.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-weather",
    instructions=(
        "Provides day-by-day weather forecasts and summaries for travel destinations. "
        "Call get_weather_summary before any packing list generation."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_TOOLS = ["get_weather_forecast", "get_weather_summary"]


@mcp.tool()
async def get_weather_forecast(destination: str, start_date: str, end_date: str) -> str:
    """
    Fetch a day-by-day weather forecast for a travel destination.

    Args:
        destination: City or country name (e.g. 'London', 'Dubai', 'New York').
        start_date:  Trip start date in YYYY-MM-DD format.
        end_date:    Trip end date in YYYY-MM-DD format.

    Returns:
        JSON array of WeatherDay objects: date, condition, temp_high, temp_low, description.
    """
    # Input validation
    if not destination.strip():
        return json.dumps({"error": "destination cannot be empty"})
    if start_date > end_date:
        return json.dumps({"error": "start_date must be before end_date"})

    logger.info("tool_get_weather_forecast", destination=destination, start=start_date, end=end_date)
    try:
        days: list[WeatherDay] = fetch_weather(destination, start_date, end_date)
        return json.dumps([d.model_dump() for d in days], indent=2)
    except Exception as exc:
        logger.error("tool_error", tool="get_weather_forecast", error=str(exc))
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_weather_summary(destination: str, start_date: str, end_date: str) -> str:
    """
    Fetch and summarise weather — dominant condition, avg temps, rainy days, recommendation.

    Args:
        destination: City or country name.
        start_date:  Trip start in YYYY-MM-DD format.
        end_date:    Trip end in YYYY-MM-DD format.

    Returns:
        JSON WeatherSummary with dominant_condition, avg_high, avg_low, rainy_days,
        recommendation, and a days[] list.
    """
    if not destination.strip():
        return json.dumps({"error": "destination cannot be empty"})

    logger.info("tool_get_weather_summary", destination=destination, start=start_date, end=end_date)
    try:
        days = fetch_weather(destination, start_date, end_date)
        summary: WeatherSummary = summarise_weather(days)
        return summary.model_dump_json(indent=2)
    except Exception as exc:
        logger.error("tool_error", tool="get_weather_summary", error=str(exc))
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    logger.info("weather_server_starting", port=settings.weather_port)
    mcp.settings.host = settings.weather_host
    mcp.settings.port = settings.weather_port
    mcp.run(transport="sse")
