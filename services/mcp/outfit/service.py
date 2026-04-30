"""Outfit generation service — GPT-4o powered outfit suggestions."""

from __future__ import annotations

import json
import os

import httpx

from shared.schemas import ClosetItem, OutfitResult, OutfitSuggestion
from shared.logger import get_logger

logger = get_logger("outfit.service")

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

_SYSTEM = """\
You are an expert personal stylist. Given a wardrobe of clothing items, weather conditions,
the user's occasion, and (optionally) the user's body + style profile, suggest 3 realistic
outfit combinations that the user can actually wear and would look good in.

Return ONLY valid JSON (no markdown) with this structure:
{
  "outfits": [
    {
      "name": "Outfit name",
      "items": [{ "id": "...", "name": "...", "category": "..." }],
      "style_notes": "...",
      "occasion_fit": "...",
      "weather_suitability": "...",
      "style_score": 8.5
    }
  ],
  "style_tips": ["tip1", "tip2"]
}

Hard rules:
- Use ONLY items from the provided wardrobe (referenced by id).
- Each outfit must contain 2–5 items, with at least one top and one bottom (or a dress/full-look).
- Avoid pairing items whose fits clash (e.g. oversized top + oversized bottom unless intentional).
- Respect the user's preferred_fit and body_type when choosing combinations.
- Avoid styles or categories listed in `avoid_categories` / `avoid_colors`.
- Make each of the 3 outfits visually distinct — do not return three near-duplicates.
- style_score is a float 0–10.
- style_tips are 2–4 short hints tailored to the weather + occasion + user style.
"""


def _format_user_profile(profile: dict | None) -> str:
    """Render the user profile compactly for the prompt; empty string when absent."""
    if not profile:
        return ""

    body = profile.get("body_profile") or {}
    style = profile.get("style_profile") or {}
    prefs = profile.get("preferences") or {}

    lines: list[str] = []

    body_bits = []
    if body.get("body_type"):     body_bits.append(f"body_type={body['body_type']}")
    if body.get("preferred_fit"): body_bits.append(f"preferred_fit={body['preferred_fit']}")
    if body.get("height_cm"):     body_bits.append(f"height={body['height_cm']}cm")
    if body.get("shirt_size"):    body_bits.append(f"shirt={body['shirt_size']}")
    if body.get("pant_size"):     body_bits.append(f"pant={body['pant_size']}")
    if body.get("shoe_size"):     body_bits.append(f"shoe={body['shoe_size']}")
    if body_bits:
        lines.append("Body: " + ", ".join(body_bits))

    if style.get("learned_style"):
        lines.append(f"Dominant style (learned from closet): {style['learned_style']}")
    if style.get("selected_styles"):
        lines.append(f"Preferred styles: {', '.join(style['selected_styles'])}")
    if style.get("favorite_colors"):
        lines.append(f"Favorite colors: {', '.join(style['favorite_colors'])}")
    if style.get("avoid_colors"):
        lines.append(f"Avoid colors: {', '.join(style['avoid_colors'])}")

    if prefs.get("avoid_categories"):
        lines.append(f"Avoid categories: {', '.join(prefs['avoid_categories'])}")
    if prefs.get("notes"):
        lines.append(f"Notes: {prefs['notes']}")

    return "\n".join(lines)


def _mock_result(closet_items: list[ClosetItem], occasion: str) -> OutfitResult:
    """Fallback when AI is unavailable."""
    logger.warning("outfit_mock_fallback")
    tops    = [i for i in closet_items if i.category == "tops"][:1]
    bottoms = [i for i in closet_items if i.category == "bottoms"][:1]
    shoes   = [i for i in closet_items if i.category == "shoes"][:1]
    items   = tops + bottoms + shoes or closet_items[:3]

    return OutfitResult(
        outfits=[
            OutfitSuggestion(
                name=f"Simple {occasion.title()} Look",
                items=items,
                style_notes="A clean, uncomplicated combination from your wardrobe.",
                occasion_fit=occasion,
                weather_suitability="Suitable for moderate conditions.",
                style_score=6.0,
            )
        ],
        style_tips=["Mix textures for visual interest.", "Accessories can elevate any look."],
    )


async def generate_outfits(
    closet_items: list[ClosetItem],
    occasion: str,
    weather: str = "",
    temperature: float | None = None,
    user_profile: dict | None = None,
) -> OutfitResult:
    """
    Generate outfit suggestions using GPT-4o.

    Args:
        closet_items: Available wardrobe items.
        occasion:     Target occasion (e.g. "casual", "formal", "beach").
        weather:      Weather condition string (e.g. "Sunny", "Rainy").
        temperature:  Temperature in Celsius.

    Returns:
        OutfitResult with up to 3 outfit suggestions and style tips.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or not closet_items:
        return _mock_result(closet_items, occasion)

    wardrobe_json = json.dumps(
        [{"id": i.id, "name": i.name, "category": i.category, "color": i.color,
          "brand": i.brand, "tags": i.tags, "occasion": i.occasion} for i in closet_items],
        indent=2,
    )

    temp_str = f"{temperature:.0f}°C" if temperature is not None else "unknown"
    profile_block = _format_user_profile(user_profile)
    user_msg_parts = [
        f"Occasion: {occasion}",
        f"Weather: {weather or 'Not specified'}, {temp_str}",
    ]
    if profile_block:
        user_msg_parts.append(f"\nUser profile:\n{profile_block}")
    user_msg_parts.append(f"\nWardrobe:\n{wardrobe_json}")
    user_msg = "\n".join(user_msg_parts)

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                _OPENAI_URL,
                json={
                    "model": _MODEL,
                    "max_tokens": 1500,
                    "temperature": 0.7,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": user_msg},
                    ],
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        return OutfitResult(**data)

    except httpx.HTTPStatusError as exc:
        logger.error("outfit_api_error", status=exc.response.status_code)
        return _mock_result(closet_items, occasion)
    except json.JSONDecodeError as exc:
        logger.error("outfit_parse_error", error=str(exc))
        return _mock_result(closet_items, occasion)
    except Exception as exc:
        logger.error("outfit_unexpected_error", error=str(exc))
        return _mock_result(closet_items, occasion)


async def get_style_tips(occasion: str, weather: str, temperature: float | None) -> list[str]:
    """Return concise styling tips without full outfit generation."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    temp_str = f"{temperature:.0f}°C" if temperature is not None else "unknown"

    if not api_key:
        return [
            f"Choose breathable fabrics for {weather.lower()} weather.",
            f"Stick to {occasion} dress code.",
            "Accessories can elevate any look.",
        ]

    prompt = (
        f"Give 5 concise style tips (as a JSON array of strings) for a {occasion} "
        f"occasion in {weather} weather at {temp_str}. Return only the JSON array."
    )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _OPENAI_URL,
                json={
                    "model": _MODEL,
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw)
    except Exception as exc:
        logger.error("style_tips_error", error=str(exc))
        return ["Layer thoughtfully for comfort and style."]
