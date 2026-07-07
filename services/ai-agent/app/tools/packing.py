"""Packing tool — generic, closet-agnostic trip checklist as a LangChain tool.

Wardrobe-matched packing (closet grounding, activities, bag-size, rewear
strategy, day-by-day outfits) lives in the api-gateway ``packing_service`` —
the single source of truth reached by the Travel Planner. This tool only
provides a generic checklist for the conversational agent, so there is no
duplicated wardrobe-matching logic here and nothing that can hallucinate a
closet item.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool


@tool
async def get_packing_checklist(
    destination: str,
    purpose: str,
    duration_days: int,
    avg_temperature: float = 20.0,
) -> str:
    """
    Return a simple generic packing checklist without wardrobe matching.

    Args:
        destination:     Travel destination.
        purpose:         Trip type.
        duration_days:   Number of days.
        avg_temperature: Average temperature in Celsius (default 20).

    Returns:
        JSON object with a checklist array of item strings.
    """
    if not destination.strip() or not purpose.strip():
        return json.dumps({"error": "destination and purpose are required"})
    days = max(1, duration_days)
    items: list[str] = [
        f"Underwear × {days}", f"Socks × {days}",
        f"T-shirts / tops × {max(3, days // 2)}",
        f"Bottoms (trousers / jeans) × {max(2, days // 3)}",
        "Comfortable walking shoes", "Sleepwear × 2",
        "Toiletries bag", "Phone charger + travel adapter",
        "Reusable water bottle", "Passport / ID + travel documents",
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
