"""
Packing MCP Server — port 8013
Builds trip packing lists from wardrobe data and weather summaries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import ClosetItem, WeatherSummary
from service import generate_packing_list

logger = get_logger("packing.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-packing",
    instructions=(
        "Generates trip packing lists from wardrobe items and weather data. "
        "Always call the weather MCP first to get weather_summary_json, then call "
        "generate_trip_packing_list with that output."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_TOOLS = ["generate_trip_packing_list", "get_packing_checklist"]


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
    Generate a complete packing list for a trip.

    Args:
        destination:          City / country name.
        start_date:           Trip start date (YYYY-MM-DD).
        end_date:             Trip end date (YYYY-MM-DD).
        purpose:              Trip type: business, leisure, beach, sport, formal, adventure.
        closet_items_json:    JSON array of closet items from the user's wardrobe.
        weather_summary_json: JSON WeatherSummary from the weather MCP server.

    Returns:
        JSON PackingResult with packing_list, missing_items, daily_plan, alerts, summary.
    """
    # Input validation
    for field, val in [
        ("destination", destination), ("start_date", start_date),
        ("end_date", end_date), ("purpose", purpose),
    ]:
        if not val.strip():
            return json.dumps({"error": f"{field} cannot be empty"})

    if start_date > end_date:
        return json.dumps({"error": "start_date must be before end_date"})

    logger.info(
        "tool_generate_trip_packing_list",
        destination=destination, start=start_date, end=end_date, purpose=purpose,
    )

    # Parse inputs
    try:
        raw_items = json.loads(closet_items_json) if closet_items_json.strip() else []
        closet_items = [ClosetItem(**item) for item in raw_items]
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid closet_items_json: {exc}"})

    try:
        weather_data = json.loads(weather_summary_json)
        weather_summary = WeatherSummary(**weather_data)
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid weather_summary_json: {exc}"})

    try:
        result = await generate_packing_list(
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            purpose=purpose,
            closet_items=closet_items,
            weather_summary=weather_summary,
        )
        return result.model_dump_json(indent=2)
    except Exception as exc:
        logger.error("tool_error", tool="generate_trip_packing_list", error=str(exc))
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_packing_checklist(
    destination: str,
    purpose: str,
    duration_days: int,
    avg_temperature: float = 20.0,
) -> str:
    """
    Return a simple generic checklist without wardrobe matching.

    Args:
        destination:     Travel destination.
        purpose:         Trip type.
        duration_days:   Number of days.
        avg_temperature: Average temperature in Celsius (default 20).

    Returns:
        JSON array of packing item strings.
    """
    if not destination.strip() or not purpose.strip():
        return json.dumps({"error": "destination and purpose are required"})

    logger.info(
        "tool_get_packing_checklist",
        destination=destination, purpose=purpose, days=duration_days,
    )

    days = max(1, duration_days)
    items: list[str] = [
        f"Underwear × {days}",
        f"Socks × {days}",
        f"T-shirts / tops × {max(3, days // 2)}",
        f"Bottoms (trousers / jeans) × {max(2, days // 3)}",
        "Comfortable walking shoes",
        "Sleepwear × 2",
        "Toiletries bag",
        "Phone charger + travel adapter",
        "Reusable water bottle",
        "Passport / ID + travel documents",
    ]

    if purpose.lower() == "business":
        items += ["Formal shirt × 2", "Suit / blazer", "Dress shoes", "Business cards"]
    if purpose.lower() in {"beach", "leisure"} or avg_temperature >= 28:
        items += ["Swimwear × 2", "Sunscreen SPF 50+", "Sunglasses", "Beach towel", "Flip-flops"]
    if avg_temperature < 10:
        items += ["Heavy jacket / coat", "Thermal layers × 2", "Gloves", "Beanie"]
    if avg_temperature < 0:
        items += ["Insulated waterproof boots", "Scarf"]

    return json.dumps({"checklist": items, "destination": destination, "duration_days": days}, indent=2)


if __name__ == "__main__":
    logger.info("packing_server_starting", port=settings.packing_port)
    mcp.settings.host = settings.packing_host
    mcp.settings.port = settings.packing_port
    mcp.run(transport="sse")
