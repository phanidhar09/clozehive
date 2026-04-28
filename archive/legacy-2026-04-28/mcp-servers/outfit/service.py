"""
Outfit service — GPT-4o powered outfit recommendation engine.
Given a list of closet items + context, returns 3 styled outfit combinations.
"""

from __future__ import annotations

import json
import random

from openai import AsyncOpenAI

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import ClosetItem, OutfitResult, OutfitSuggestion

logger = get_logger(__name__)

_SYSTEM_PROMPT = """
You are a professional fashion stylist with deep knowledge of colour theory,
occasion dressing, and sustainable fashion. You create outfit combinations that
are practical, stylish, and appropriate for the occasion and weather.
""".strip()


def _build_user_prompt(
    items: list[ClosetItem],
    occasion: str,
    weather: str,
    temperature: float,
) -> str:
    item_lines = "\n".join(
        f"  - [{i.id or idx}] {i.name} ({i.category}, {i.color}, {i.fabric or 'unknown fabric'})"
        for idx, i in enumerate(items)
    )
    return f"""
Create 3 distinct outfit combinations from the wardrobe below.

OCCASION: {occasion}
WEATHER:  {weather}
TEMP:     {temperature}°C

WARDROBE:
{item_lines}

Return ONLY valid JSON (no markdown) with this exact schema:
{{
  "outfits": [
    {{
      "name": "<outfit name>",
      "item_ids": ["<id or index>"],
      "items": [{{"name": "<name>", "category": "<cat>", "color": "<colour>", "why": "<reason>"}}],
      "explanation": "<overall styling rationale>",
      "style_score": <1-10>,
      "occasion_fit": "<how it suits the occasion>",
      "weather_fit": "<how it handles the weather>"
    }}
  ]
}}
""".strip()


async def generate_outfits(
    closet_items: list[ClosetItem],
    occasion: str = "casual",
    weather: str = "mild",
    temperature: float = 20.0,
) -> OutfitResult:
    """
    Generate 3 outfit suggestions from the provided closet items.

    Args:
        closet_items: List of ClosetItem objects from the user's wardrobe.
        occasion:    Target occasion (casual / formal / business / athletic …).
        weather:     Weather description (sunny / rainy / cold / humid …).
        temperature: Temperature in Celsius.

    Returns:
        OutfitResult containing 3 outfit suggestions.
    """
    settings = get_settings()
    logger.info(
        "Generating outfits — %d items, occasion=%s, weather=%s, temp=%.1f°C",
        len(closet_items),
        occasion,
        weather,
        temperature,
    )

    if not closet_items:
        logger.warning("No closet items provided — returning mock outfits")
        return _mock_result(occasion, weather, temperature)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.8,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_user_prompt(closet_items, occasion, weather, temperature),
                },
            ],
        )

        raw = response.choices[0].message.content or "{}"
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)

        outfits = [OutfitSuggestion(**o) for o in data.get("outfits", [])]
        logger.info("Generated %d outfit suggestions", len(outfits))

        return OutfitResult(
            outfits=outfits,
            occasion=occasion,
            weather=weather,
            temperature=temperature,
        )

    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error from GPT outfit: %s", exc)
        return _mock_result(occasion, weather, temperature)
    except Exception as exc:
        logger.error("Outfit API error: %s", exc, exc_info=True)
        return _mock_result(occasion, weather, temperature)


def _mock_result(occasion: str, weather: str, temperature: float) -> OutfitResult:
    """Deterministic fallback when the API is unavailable."""
    logger.warning("Returning mock outfit result")
    return OutfitResult(
        outfits=[
            OutfitSuggestion(
                name="Classic Everyday",
                item_ids=[],
                items=[],
                explanation="A timeless, versatile outfit suitable for most occasions.",
                style_score=7,
                occasion_fit=f"Works well for {occasion}",
                weather_fit=f"Comfortable in {weather} conditions",
            ),
            OutfitSuggestion(
                name="Smart Casual",
                item_ids=[],
                items=[],
                explanation="Elevated casual look with polished details.",
                style_score=8,
                occasion_fit=f"Ideal for {occasion}",
                weather_fit=f"Layered for {weather}",
            ),
            OutfitSuggestion(
                name="Minimalist Chic",
                item_ids=[],
                items=[],
                explanation="Clean lines and neutral tones for effortless style.",
                style_score=9,
                occasion_fit=f"Perfect for {occasion}",
                weather_fit=f"Breathable for {temperature:.0f}°C",
            ),
        ],
        occasion=occasion,
        weather=weather,
        temperature=temperature,
    )
