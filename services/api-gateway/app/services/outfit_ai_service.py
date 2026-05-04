"""Production-grade AI outfit scoring and recommendation engine.

Scoring formula (max 100):
  color        25%  — palette harmony, contrast
  occasion     25%  — suitability for stated occasion
  fit          20%  — size/fit compatibility across pieces
  style        15%  — coherent style narrative
  weather      10%  — seasonal/weather appropriateness
  preference    5%  — alignment with user profile preferences
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services import ai_service

logger = get_logger("outfit_ai_service")

# ── System prompts ─────────────────────────────────────────────────────────────

_GENERATE_SYSTEM_PROMPT = """\
You are ClozeHive AI, an expert fashion AI for ClosetIQ with mastery of color theory, \
style principles, and occasion dressing.

SCORING FORMULA — score_breakdown values must sum EXACTLY to matching_score (integer 0–100):
  color      max 25  Color Compatibility: harmony, contrast, palette cohesion
  occasion   max 25  Occasion Match: suitability for stated occasion
  fit        max 20  Fit & Size Alignment: size/fit compatibility across pieces
  style      max 15  Style Consistency: coherent style narrative
  weather    max 10  Weather Suitability: appropriate for weather/season (use 7 if no weather)
  preference max  5  User Preference Match: alignment with stated user preferences

STRICT RULES:
1. ONLY use items from the provided wardrobe list. NEVER invent items.
2. Use the exact id and name from each item.
3. matching_score MUST equal color + occasion + fit + style + weather + preference exactly.
4. Generate exactly 3 outfits with clearly different aesthetics (e.g., casual / smart-casual / bold).
5. improvements: actionable swaps with specific reasons ("Replace black sneakers with white for better contrast").
6. issues: specific problems only ("Navy and black lack contrast — both dark tones compete").
7. styling_tips: 3–5 practical, occasion-specific tips per outfit.
8. For each unused item provide a concrete why_not_selected reason.
9. confidence: float 0.0–1.0 reflecting wardrobe adequacy for this occasion.
10. Return ONLY valid JSON — no markdown fences, no prose outside JSON.

EXACT RESPONSE SCHEMA:
{
  "outfits": [
    {
      "items": {
        "top":        {"id": "uuid", "name": "...", "category": "tops",       "color": "..."},
        "bottom":     {"id": "uuid", "name": "...", "category": "bottoms",    "color": "..."},
        "footwear":   {"id": "uuid", "name": "...", "category": "shoes",      "color": "..."},
        "outerwear":  {"id": "uuid", "name": "...", "category": "outerwear",  "color": "..."},
        "accessories":[{"id": "uuid", "name": "...", "category": "accessories"}]
      },
      "matching_score": 87,
      "confidence": 0.92,
      "score_breakdown": {
        "color": 22, "occasion": 23, "fit": 18, "style": 12, "weather": 8, "preference": 4
      },
      "recommendations": {
        "improvements": ["..."],
        "issues": ["..."],
        "styling_tips": ["..."]
      },
      "reasoning": "One-paragraph explanation of why this outfit works."
    }
  ],
  "unused_items": [
    {"id": "uuid", "name": "...", "category": "...", "why_not_selected": "..."}
  ],
  "style_tips": ["General tip 1", "General tip 2"]
}"""


_ANALYZE_SYSTEM_PROMPT = """\
You are ClozeHive AI, an expert fashion AI for ClosetIQ.

The user has hand-picked specific items and placed them together as an outfit. \
Analyse this exact combination, score it rigorously, and provide actionable feedback.

SCORING FORMULA — score_breakdown values must sum EXACTLY to matching_score (integer 0–100):
  color      max 25  Color Compatibility: harmony, contrast, palette cohesion
  occasion   max 25  Occasion Match: suitability for stated occasion
  fit        max 20  Fit & Size Alignment: size/fit compatibility across pieces
  style      max 15  Style Consistency: coherent style narrative
  weather    max 10  Weather Suitability: appropriate for weather/season (use 7 if none provided)
  preference max  5  User Preference Match: alignment with stated user preferences

STRICT RULES:
1. Only reference items in the provided selected_outfit_items list. Do NOT add items.
2. matching_score MUST equal color + occasion + fit + style + weather + preference exactly.
3. improvements: specific actionable swaps ("Try white sneakers instead of black for visual lift").
4. issues: concrete problems only, not vague ("The olive jacket clashes with the burgundy trousers").
5. styling_tips: 3–5 practical tips for exactly this combination (tuck, belt, layer, accessorise).
6. missing_pieces: list category names that would complete the look (e.g. "outerwear", "belt").
7. confidence: 0.0–1.0 — how certain the AI is about the scoring.
8. Return ONLY valid JSON — no markdown fences, no prose outside JSON.

EXACT RESPONSE SCHEMA:
{
  "outfit": {
    "items": {
      "top":        {"id": "uuid", "name": "...", "category": "tops",       "color": "..."},
      "bottom":     {"id": "uuid", "name": "...", "category": "bottoms",    "color": "..."},
      "footwear":   {"id": "uuid", "name": "...", "category": "shoes",      "color": "..."},
      "outerwear":  {"id": "uuid", "name": "...", "category": "outerwear",  "color": "..."},
      "accessories":[{"id": "uuid", "name": "...", "category": "accessories"}]
    },
    "matching_score": 84,
    "confidence": 0.89,
    "score_breakdown": {
      "color": 21, "occasion": 22, "fit": 17, "style": 12, "weather": 8, "preference": 4
    },
    "recommendations": {
      "improvements": ["..."],
      "issues": ["..."],
      "styling_tips": ["..."]
    },
    "reasoning": "One-paragraph explanation of the outfit's strengths and weaknesses."
  },
  "missing_pieces": ["outerwear", "belt"],
  "style_tips": ["General tip 1", "General tip 2"]
}"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].removeprefix("json").strip()
        if "```" in text:
            text = text[: text.index("```")]
    return text.strip()


def _categorize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    slots: dict[str, Any] = {
        "top": None,
        "bottom": None,
        "footwear": None,
        "outerwear": None,
        "accessories": [],
    }
    for item in items:
        cat = (item.get("category") or "").lower()
        if cat in ("tops", "dresses") and slots["top"] is None:
            slots["top"] = item
        elif cat == "bottoms" and slots["bottom"] is None:
            slots["bottom"] = item
        elif cat == "shoes" and slots["footwear"] is None:
            slots["footwear"] = item
        elif cat == "outerwear" and slots["outerwear"] is None:
            slots["outerwear"] = item
        elif cat == "accessories":
            slots["accessories"].append(item)
    return slots


def _item_for_ai(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id":         str(item.get("id", "")),
        "name":       item.get("name", ""),
        "category":   item.get("category", ""),
        "color":      item.get("color", "") or "",
        "fabric":     item.get("fabric", "") or "",
        "pattern":    item.get("pattern", "") or "",
        "season":     item.get("season", "") or "",
        "occasion":   item.get("occasion", []) or [],
        "size":       item.get("size", "") or "",
        "brand":      item.get("brand", "") or "",
        "tags":       item.get("tags", []) or [],
        "wear_count": item.get("wear_count", 0),
    }


# ── Fallback mock results ──────────────────────────────────────────────────────

def _mock_generate(closet_items: list[dict[str, Any]], occasion: str) -> dict[str, Any]:
    items = closet_items[:5]
    return {
        "outfits": [
            {
                "items": _categorize_items(items),
                "matching_score": 65,
                "confidence": 0.5,
                "score_breakdown": {
                    "color": 16, "occasion": 16, "fit": 13, "style": 10, "weather": 6, "preference": 4,
                },
                "recommendations": {
                    "improvements": ["Add more closet items for richer outfit generation."],
                    "issues": [],
                    "styling_tips": ["Start with a neutral base to maximise combination potential."],
                },
                "reasoning": "Limited wardrobe detected — this is a best-effort combination. Add more items for higher quality suggestions.",
            }
        ],
        "unused_items": [],
        "style_tips": ["Build a capsule wardrobe with 3–5 versatile basics per category."],
    }


def _mock_analyze(selected_items: list[dict[str, Any]], occasion: str) -> dict[str, Any]:
    return {
        "outfit": {
            "items": _categorize_items(selected_items),
            "matching_score": 70,
            "confidence": 0.5,
            "score_breakdown": {
                "color": 18, "occasion": 17, "fit": 14, "style": 10, "weather": 7, "preference": 4,
            },
            "recommendations": {
                "improvements": ["Review the color palette for better tonal harmony."],
                "issues": [],
                "styling_tips": ["Ensure the outfit matches the occasion you have in mind."],
            },
            "reasoning": "AI scoring is temporarily unavailable. This is a placeholder analysis — try again shortly.",
        },
        "missing_pieces": [],
        "style_tips": ["Complete your closet profile to get personalised tips."],
    }


# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_outfits(
    closet_items: list[dict[str, Any]],
    occasion: str,
    weather: str = "",
    temperature: float | None = None,
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate 3 diverse, scored outfit combinations from the user's full wardrobe."""
    if not closet_items:
        return _mock_generate(closet_items, occasion)

    payload = json.dumps(
        {
            "mode": "generate",
            "occasion": occasion,
            "weather_condition": weather or "mild",
            "temperature_celsius": temperature,
            "user_profile": user_profile or {},
            "wardrobe": [_item_for_ai(i) for i in closet_items],
        },
        default=str,
    )

    try:
        raw = await ai_service.chat(
            [{"role": "user", "content": payload}],
            _GENERATE_SYSTEM_PROMPT,
        )
        data = json.loads(_clean_json(raw))
        if isinstance(data, dict) and "outfits" in data:
            return data
    except json.JSONDecodeError:
        logger.warning("outfit_ai_generate_bad_json", occasion=occasion)
    except Exception as exc:
        logger.warning("outfit_ai_generate_failed", error=str(exc), occasion=occasion)

    return _mock_generate(closet_items, occasion)


async def analyze_outfit(
    selected_items: list[dict[str, Any]],
    occasion: str,
    weather: str = "",
    temperature: float | None = None,
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score and provide recommendations for a specific outfit combination chosen by the user."""
    if not selected_items:
        return _mock_analyze(selected_items, occasion)

    payload = json.dumps(
        {
            "mode": "analyze",
            "occasion": occasion,
            "weather_condition": weather or "mild",
            "temperature_celsius": temperature,
            "user_profile": user_profile or {},
            "selected_outfit_items": [_item_for_ai(i) for i in selected_items],
        },
        default=str,
    )

    try:
        raw = await ai_service.chat(
            [{"role": "user", "content": payload}],
            _ANALYZE_SYSTEM_PROMPT,
        )
        data = json.loads(_clean_json(raw))
        if isinstance(data, dict) and "outfit" in data:
            return data
    except json.JSONDecodeError:
        logger.warning("outfit_ai_analyze_bad_json", occasion=occasion)
    except Exception as exc:
        logger.warning("outfit_ai_analyze_failed", error=str(exc), occasion=occasion)

    return _mock_analyze(selected_items, occasion)
