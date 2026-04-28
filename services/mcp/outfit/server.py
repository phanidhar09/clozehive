"""
Outfit MCP Server — port 8012
Generates AI-powered outfit suggestions from the user's wardrobe.
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
from shared.schemas import ClosetItem
from service import generate_outfits, get_style_tips

logger = get_logger("outfit.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-outfit",
    instructions=(
        "Generates outfit combinations from a user's wardrobe for a given occasion and weather. "
        "Pass closet_items_json as a JSON array of wardrobe items."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_TOOLS = ["generate_outfit_suggestions", "get_style_tips"]


@mcp.tool()
async def generate_outfit_suggestions(
    closet_items_json: str,
    occasion: str,
    weather: str = "",
    temperature: float = 20.0,
) -> str:
    """
    Generate outfit suggestions from the user's wardrobe.

    Args:
        closet_items_json: JSON array of closet items (id, name, category, color, tags…).
        occasion:          Target occasion — casual, formal, sport, beach, business, etc.
        weather:           Weather condition string, e.g. "Sunny", "Rainy".
        temperature:       Temperature in Celsius (default 20).

    Returns:
        JSON OutfitResult with outfits[] and style_tips[].
    """
    if not closet_items_json.strip():
        return json.dumps({"error": "closet_items_json cannot be empty"})
    if not occasion.strip():
        return json.dumps({"error": "occasion cannot be empty"})

    logger.info(
        "tool_generate_outfit_suggestions",
        occasion=occasion, weather=weather, temperature=temperature,
    )

    try:
        raw_items = json.loads(closet_items_json)
        items = [ClosetItem(**item) for item in raw_items]
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid closet_items_json: {exc}"})

    try:
        result = await generate_outfits(items, occasion, weather, temperature)
        return result.model_dump_json(indent=2)
    except Exception as exc:
        logger.error("tool_error", tool="generate_outfit_suggestions", error=str(exc))
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_outfit_style_tips(
    occasion: str,
    weather: str = "",
    temperature: float = 20.0,
) -> str:
    """
    Get concise styling tips for an occasion and weather without full outfit generation.

    Args:
        occasion:    Target occasion.
        weather:     Weather condition string.
        temperature: Temperature in Celsius.

    Returns:
        JSON array of style tip strings.
    """
    if not occasion.strip():
        return json.dumps({"error": "occasion cannot be empty"})

    logger.info("tool_get_style_tips", occasion=occasion, weather=weather)
    try:
        tips = await get_style_tips(occasion, weather, temperature)
        return json.dumps(tips, indent=2)
    except Exception as exc:
        logger.error("tool_error", tool="get_outfit_style_tips", error=str(exc))
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    logger.info("outfit_server_starting", port=settings.outfit_port)
    mcp.settings.host = settings.outfit_host
    mcp.settings.port = settings.outfit_port
    mcp.run(transport="sse")
