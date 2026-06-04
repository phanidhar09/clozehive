"""Consolidated outfit suggestion service."""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services import ai_service

logger = get_logger("outfit_service")


def _mock_result(closet_items: list[dict[str, Any]], occasion: str) -> dict[str, Any]:
    items = closet_items[:3]
    return {
        "outfits": [{
            "name": f"Simple {occasion.title()} Look",
            "items": items,
            "style_notes": "A clean combination from your wardrobe.",
            "occasion_fit": occasion,
            "weather_suitability": "Suitable for moderate conditions.",
            "style_score": 6.0,
        }],
        "style_tips": ["Use layers to adapt the outfit.", "Keep accessories intentional."],
    }


def _style_context_from_profile(user_profile: dict[str, Any] | None) -> str:
    if not user_profile:
        return ""
    t = user_profile.get("style_profile_context_text")
    if isinstance(t, str) and t.strip():
        return f"\n\n{t.strip()}\n"
    return ""


async def generate_outfits(
    closet_items: list[dict[str, Any]],
    occasion: str,
    weather: str = "",
    temperature: float | None = None,
    user_profile: dict[str, Any] | None = None,
    fashion_context: str = "",
    history_context: str = "",
) -> dict[str, Any]:
    if not closet_items:
        return _mock_result(closet_items, occasion)

    style_block = _style_context_from_profile(user_profile)
    rag_block = ""
    if fashion_context.strip():
        rag_block += f"\n\n[FASHION KNOWLEDGE]\n{fashion_context.strip()}\n[END FASHION KNOWLEDGE]"
    if history_context.strip():
        rag_block += f"\n\n[PAST OUTFIT HISTORY]\n{history_context.strip()}\n[END PAST OUTFIT HISTORY]"
    system_prompt = f"""You are an expert ClozeHive personal stylist.
Use positive, supportive language. Never criticise the user's body. Honour avoided colors and climate preferences when listed in the user profile context.
Return ONLY valid JSON with shape:
{{"outfits":[{{"name":"","items":[{{"id":"","name":"","category":""}}],"style_notes":"","occasion_fit":"","weather_suitability":"","style_score":8.5}}],"style_tips":[]}}
Hard rules: only use items from the provided wardrobe, refer to exact item names, and do not invent missing items.{style_block}{rag_block}"""
    user_prompt = json.dumps({
        "occasion": occasion,
        "weather": weather,
        "temperature_c": temperature,
        "user_profile": user_profile,
        "wardrobe": closet_items,
    }, default=str)
    try:
        response = await ai_service.chat([{"role": "user", "content": user_prompt}], system_prompt)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        data = json.loads(text)
        if isinstance(data, dict) and "outfits" in data:
            return data
    except json.JSONDecodeError:
        logger.warning("outfit_ai_invalid_json", occasion=occasion)
    except Exception as exc:
        logger.warning("outfit_ai_failed_fallback", error=str(exc), occasion=occasion)
    return _mock_result(closet_items, occasion)
