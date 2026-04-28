"""
Weather MCP Server — port 8004
Exposes deterministic mock weather data as MCP tools.

Run:
    python server.py
    # or
    uvicorn server:mcp_app --port 8004
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make shared importable from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import WeatherDay, WeatherSummary
from service import fetch_weather, summarise_weather

logger = get_logger("weather.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-weather",
    instructions=(
        "Weather service for CLOZEHIVE. Provides day-by-day weather forecasts "
        "and summaries for travel destinations. Always call fetch_weather before "
        "summarise_weather to get fresh data."
    ),
)


@mcp.tool()
async def get_weather_forecast(
    destination: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Fetch a day-by-day weather forecast for a travel destination.

    Args:
        destination: City or country name (e.g. 'London', 'Dubai', 'New York').
        start_date:  Trip start date in YYYY-MM-DD format.
        end_date:    Trip end date in YYYY-MM-DD format.

    Returns:
        JSON string — list of WeatherDay objects with date, condition,
        temp_high, temp_low, and description fields.
    """
    logger.info("Tool: get_weather_forecast(%s, %s → %s)", destination, start_date, end_date)
    days: list[WeatherDay] = fetch_weather(destination, start_date, end_date)
    result = [d.model_dump() for d in days]
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_weather_summary(
    destination: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Fetch and summarise weather for a destination — dominant condition, average
    temperatures, rainy day count, and a packing recommendation string.

    Args:
        destination: City or country name.
        start_date:  Trip start date in YYYY-MM-DD format.
        end_date:    Trip end date in YYYY-MM-DD format.

    Returns:
        JSON string — WeatherSummary with dominant_condition, avg_high, avg_low,
        rainy_days, recommendation, and a 'days' list.
    """
    logger.info("Tool: get_weather_summary(%s, %s → %s)", destination, start_date, end_date)
    days: list[WeatherDay] = fetch_weather(destination, start_date, end_date)
    summary: WeatherSummary = summarise_weather(days)
    return summary.model_dump_json(indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting Weather MCP server on %s:%d",
        settings.weather_host,
        settings.weather_port,
    )
    mcp.run(
        transport="sse",
        host=settings.weather_host,
        port=settings.weather_port,
    )
