"""Outfit tool — GPT-4o powered outfit suggestions wrapped as LangChain tools."""

from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool

from app.tools.schemas import ClosetItem, OutfitResult, OutfitSuggestion

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
- ONLY recommend items from the user's wardrobe listed above.
- Use ONLY items from the provided wardrobe (referenced by id).
- Each outfit must contain 2–5 items, with at least one top and one bottom (or a dress/full-look).
- Make each of the 3 outfits visually distinct — do not return three near-duplicates.
- style_score is a float 0–10.
- style_tips are 2–4 short hints tailored to the weather + occasion + user style.
"""


def _format_user_profile(profile: dict | None) -> str:
    if not profile:
        return ""
    body  = profile.get("body_profile") or {}
    style = profile.get("style_profile") or {}
    prefs = profile.get("preferences") or {}
    lines: list[str] = []
    body_bits = []
    if body.get("body_type"):     body_bits.append(f"body_type={body['body_type']}")
    if body.get("preferred_fit"): body_bits.append(f"preferred_fit={body['preferred_fit']}")
    if body_bits:
        lines.append("Body: " + ", ".join(body_bits))
    if style.get("selected_styles"):
        lines.append(f"Preferred styles: {', '.join(style['selected_styles'])}")
    if style.get("favorite_colors"):
        lines.append(f"Favorite colors: {', '.join(style['favorite_colors'])}")
    if style.get("avoid_colors"):
        lines.append(f"Avoid colors: {', '.join(style['avoid_colors'])}")
    if prefs.get("avoid_categories"):
        lines.append(f"Avoid categories: {', '.join(prefs['avoid_categories'])}")
    return "\n".join(lines)


def _mock_result(closet_items: list[ClosetItem], occasion: str) -> OutfitResult:
    tops    = [i for i in closet_items if i.category == "tops"][:1]
    bottoms = [i for i in closet_items if i.category == "bottoms"][:1]
    shoes   = [i for i in closet_items if i.category == "shoes"][:1]
    items   = tops + bottoms + shoes or closet_items[:3]
    return OutfitResult(
        outfits=[OutfitSuggestion(
            name=f"Simple {occasion.title()} Look",
            items=items,
            style_notes="A clean, uncomplicated combination from your wardrobe.",
            occasion_fit=occasion,
            weather_suitability="Suitable for moderate conditions.",
            style_score=6.0,
        )],
        style_tips=["Mix textures for visual interest.", "Accessories can elevate any look."],
    )


async def _generate_outfits(
    closet_items: list[ClosetItem],
    occasion: str,
    weather: str = "",
    temperature: float | None = None,
    user_profile: dict | None = None,
) -> OutfitResult:
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
    parts = [f"Occasion: {occasion}", f"Weather: {weather or 'Not specified'}, {temp_str}"]
    if profile_block:
        parts.append(f"\nUser profile:\n{profile_block}")
    parts.append(f"\nWardrobe:\n{wardrobe_json}")

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
                        {"role": "user",   "content": "\n".join(parts)},
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
        return OutfitResult(**json.loads(raw))

    except Exception:
        return _mock_result(closet_items, occasion)


async def _get_style_tips(occasion: str, weather: str, temperature: float | None) -> list[str]:
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
                json={"model": _MODEL, "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return ["Layer thoughtfully for comfort and style."]


# ── LangChain tools ───────────────────────────────────────────────────────────

@tool
async def generate_outfit_suggestions(
    closet_items_json: str,
    occasion: str,
    weather: str = "",
    temperature: float = 20.0,
    user_profile_json: str = "",
) -> str:
    """
    Generate outfit suggestions from the user's wardrobe.

    Args:
        closet_items_json: JSON array of closet items (id, name, category, color, tags…).
        occasion:          Target occasion — casual, formal, sport, beach, business, etc.
        weather:           Weather condition string, e.g. "Sunny", "Rainy".
        temperature:       Temperature in Celsius (default 20).
        user_profile_json: Optional JSON object with body_profile / style_profile / preferences.

    Returns:
        JSON OutfitResult with outfits[] and style_tips[].
    """
    if not closet_items_json.strip():
        return json.dumps({"error": "closet_items_json cannot be empty"})
    if not occasion.strip():
        return json.dumps({"error": "occasion cannot be empty"})
    try:
        items = [ClosetItem(**i) for i in json.loads(closet_items_json)]
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"Invalid closet_items_json: {exc}"})

    user_profile: dict | None = None
    if user_profile_json.strip():
        try:
            parsed = json.loads(user_profile_json)
            if isinstance(parsed, dict):
                user_profile = parsed
        except json.JSONDecodeError:
            pass

    try:
        result = await _generate_outfits(items, occasion, weather, temperature, user_profile)
        return result.model_dump_json(indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@tool
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
    try:
        tips = await _get_style_tips(occasion, weather, temperature)
        return json.dumps(tips, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
