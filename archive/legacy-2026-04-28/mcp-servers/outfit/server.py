"""
Outfit MCP Server — port 8002
Exposes GPT-4o outfit recommendation as MCP tools.

Run:
    python server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import ClosetItem, OutfitResult
from service import generate_outfits

logger = get_logger("outfit.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-outfit",
    instructions=(
        "Outfit recommendation service for CLOZEHIVE. Takes the user's closet items "
        "and context (occasion, weather, temperature) and returns 3 styled outfit "
        "combinations with explanations and style scores. "
        "Pass closet_items as a JSON array of objects with at minimum: name, category, color."
    ),
)


@mcp.tool()
async def generate_outfit_suggestions(
    closet_items_json: str,
    occasion: str = "casual",
    weather: str = "mild",
    temperature: float = 20.0,
) -> str:
    """
    Generate 3 outfit suggestions from the user's wardrobe.

    Args:
        closet_items_json: JSON array of closet item objects. Each object needs at minimum:
                           name (str), category (str), color (str).
                           Optional: fabric, pattern, season, occasion[], tags[], id.
        occasion:          Target occasion. One of: casual, formal, business, athletic,
                           evening, beach, outdoor, travel. Defaults to 'casual'.
        weather:           Current weather description: sunny, rainy, cold, hot, mild, windy.
                           Defaults to 'mild'.
        temperature:       Temperature in Celsius. Defaults to 20.0.

    Returns:
        JSON string — OutfitResult with:
          outfits[]: list of OutfitSuggestion (name, item_ids, items, explanation,
                     style_score, occasion_fit, weather_fit)
          occasion, weather, temperature.
    """
    logger.info(
        "Tool: generate_outfit_suggestions(occasion=%s, weather=%s, temp=%.1f)",
        occasion, weather, temperature,
    )

    raw_items: list[dict] = json.loads(closet_items_json)
    closet_items = [ClosetItem(**item) for item in raw_items]

    result: OutfitResult = await generate_outfits(closet_items, occasion, weather, temperature)
    return result.model_dump_json(indent=2)


@mcp.tool()
async def get_style_tips(
    occasion: str,
    weather: str,
    preferences: str = "",
) -> str:
    """
    Get general style tips for an occasion and weather combination without needing
    closet items. Useful for quick styling advice.

    Args:
        occasion:    Target occasion (casual / formal / business / athletic / beach).
        weather:     Weather description (sunny / rainy / cold / hot / mild).
        preferences: Optional comma-separated style preferences, e.g. 'minimalist, sustainable'.

    Returns:
        JSON string with a 'tips' list of styling advice strings.
    """
    logger.info("Tool: get_style_tips(occasion=%s, weather=%s)", occasion, weather)

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = (
        f"Give 5 concise style tips for a {occasion} occasion in {weather} weather."
        + (f" The person prefers: {preferences}." if preferences else "")
        + " Return ONLY a JSON array of strings, no markdown."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.7,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content or "[]"
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        tips: list[str] = json.loads(raw)
    except Exception as exc:
        logger.warning("Style tips API error: %s", exc)
        tips = [
            f"Dress appropriately for {occasion} — comfort and context matter.",
            f"Layer up for {weather} weather.",
            "Choose neutral colours for maximum versatility.",
            "Invest in quality basics that mix and match easily.",
            "Accessories can transform any outfit — use them intentionally.",
        ]

    return json.dumps({"tips": tips}, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting Outfit MCP server on %s:%d",
        settings.outfit_host,
        settings.outfit_port,
    )
    mcp.run(
        transport="sse",
        host=settings.outfit_host,
        port=settings.outfit_port,
    )
