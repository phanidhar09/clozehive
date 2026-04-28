"""
Packing MCP Server — port 8003
Exposes smart travel packing list generation as MCP tools.

The packing tool expects a pre-fetched weather summary JSON string (from the
weather MCP server). The LangChain agent is responsible for calling
weather.get_weather_summary first, then passing the result here.

Run:
    python server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import ClosetItem, PackingResult, WeatherSummary
from service import generate_packing_list

logger = get_logger("packing.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-packing",
    instructions=(
        "Travel packing service for CLOZEHIVE. Builds a smart packing list by matching "
        "required clothing categories against the user's closet, then creates a daily "
        "outfit plan for the trip duration. "
        "IMPORTANT: Always call the weather server's get_weather_summary tool first and "
        "pass the result as weather_summary_json to generate_trip_packing_list."
    ),
)


@mcp.tool()
async def generate_trip_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items_json: str,
    weather_summary_json: str,
) -> str:
    """
    Build a complete packing list for a trip, matched against the user's closet.

    Args:
        destination:          City or country name (e.g. 'Paris', 'Tokyo').
        start_date:           Trip start in YYYY-MM-DD format.
        end_date:             Trip end in YYYY-MM-DD format.
        purpose:              Trip purpose: business | beach | hiking | casual | wedding |
                              conference | adventure | holiday.
        closet_items_json:    JSON array of closet item objects (name, category, color, …).
        weather_summary_json: JSON object from weather server's get_weather_summary tool.
                              Must contain: dominant_condition, avg_high, avg_low,
                              rainy_days, recommendation, days[].

    Returns:
        JSON string — PackingResult with:
          destination, start_date, end_date, duration_days, trip_type,
          weather_summary{}, packing_list[], missing_items[], daily_plan[],
          alerts[], packing_item_ids[].
    """
    logger.info(
        "Tool: generate_trip_packing_list(dest=%s, %s → %s, purpose=%s)",
        destination, start_date, end_date, purpose,
    )

    raw_items: list[dict] = json.loads(closet_items_json)
    closet_items = [ClosetItem(**item) for item in raw_items]

    weather_data: dict = json.loads(weather_summary_json)
    weather_summary = WeatherSummary(**weather_data)

    result: PackingResult = await generate_packing_list(
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        purpose=purpose,
        closet_items=closet_items,
        weather_summary=weather_summary,
    )
    return result.model_dump_json(indent=2)


@mcp.tool()
async def get_packing_checklist(
    trip_type: str,
    duration_days: int,
    avg_temperature: float,
) -> str:
    """
    Get a generic packing checklist without needing closet data.
    Useful for quick trip planning or when no closet items are available.

    Args:
        trip_type:       Type of trip: business | beach | hiking | casual | winter.
        duration_days:   Number of days for the trip (1–30).
        avg_temperature: Average daytime temperature in Celsius.

    Returns:
        JSON string — {'checklist': [{'category': str, 'quantity': int, 'notes': str}]}.
    """
    logger.info(
        "Tool: get_packing_checklist(type=%s, days=%d, temp=%.1f°C)",
        trip_type, duration_days, avg_temperature,
    )

    shirts  = min(duration_days, 5)
    pants   = max(2, min(duration_days // 2 + 1, 4))
    socks   = min(duration_days, 7)

    checklist = [
        {"category": "Underwear",  "quantity": socks,  "notes": "Daily essential"},
        {"category": "Socks",      "quantity": socks,  "notes": "Daily essential"},
        {"category": "Tops/Shirts","quantity": shirts, "notes": "Rotate & re-wear"},
        {"category": "Bottoms",    "quantity": pants,  "notes": "Jeans/trousers/shorts"},
        {"category": "Shoes",      "quantity": 2,      "notes": "Comfortable + backup pair"},
    ]

    if avg_temperature < 15:
        checklist += [
            {"category": "Sweater/Jumper", "quantity": 2,  "notes": "Layering"},
            {"category": "Jacket/Coat",    "quantity": 1,  "notes": "Outer layer"},
        ]
    if avg_temperature < 5:
        checklist.append({"category": "Thermal base layer", "quantity": 2, "notes": "Cold weather essential"})

    if trip_type == "beach":
        checklist += [
            {"category": "Swimwear",    "quantity": 2, "notes": "Beach/pool"},
            {"category": "Sunglasses",  "quantity": 1, "notes": "UV protection"},
            {"category": "Sandals",     "quantity": 1, "notes": "Beach footwear"},
        ]
    elif trip_type == "business":
        checklist += [
            {"category": "Formal shirt/blouse", "quantity": 2, "notes": "Meetings"},
            {"category": "Blazer/Suit jacket",  "quantity": 1, "notes": "Professional"},
        ]
    elif trip_type == "hiking":
        checklist += [
            {"category": "Hiking boots",  "quantity": 1, "notes": "Sturdy footwear"},
            {"category": "Moisture-wicking tops", "quantity": shirts, "notes": "Performance"},
            {"category": "Hiking pants",  "quantity": 2, "notes": "Durable"},
        ]

    return json.dumps({"checklist": checklist}, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting Packing MCP server on %s:%d",
        settings.packing_host,
        settings.packing_port,
    )
    mcp.run(
        transport="sse",
        host=settings.packing_host,
        port=settings.packing_port,
    )
