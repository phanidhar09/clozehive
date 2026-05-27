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
You are ClozeHive AI, an expert fashion AI with mastery of color theory, \
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
You are ClozeHive AI, an expert fashion AI.

The user has hand-picked specific items and placed them together as an outfit. \
Analyse this exact combination, score it rigorously, and provide actionable feedback.

USER STYLE PROFILE:
The JSON payload includes user_profile which may contain style_profile_context_text and \
user_style_profile. Use them to assess fit, size alignment, color likes/dislikes, and climate \
preferences. If profile data is missing, fall back to the wardrobe items and occasion only. \
Never make judgmental or negative comments about the user's body — keep language positive, neutral, \
and focused on styling, comfort, and fit. Do not recommend fits (tight, cropped, bodycon, etc.) \
unless they appear in the user's fit preferences. Avoid colours the user dislikes. Prefer favourite \
colours when sensible.

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
8. fit_confidence: integer 0–100 — confidence that silhouettes and sizes work for this user's profile.
9. occasion_match, style_match: one of "High", "Medium", "Low".
10. size_profile_match: one of "High", "Medium", "Low", "Unknown".
11. body_profile_notes: short positive note on why silhouettes work for this user's stated preferences.
12. why_it_works: one succinct sentence; may overlap reasoning.
13. what_to_improve: 0–4 bullet strings for quick wins (can duplicate improvements).
14. Return ONLY valid JSON — no markdown fences, no prose outside JSON.

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
    "fit_confidence": 82,
    "score_breakdown": {
      "color": 21, "occasion": 22, "fit": 17, "style": 12, "weather": 8, "preference": 4
    },
    "occasion_match": "High",
    "style_match": "Medium",
    "size_profile_match": "High",
    "recommendations": {
      "improvements": ["..."],
      "issues": ["..."],
      "styling_tips": ["..."]
    },
    "fit_notes": "Positive note on fit relative to user profile (may mirror body_profile_notes).",
    "body_profile_notes": "Positive explanation referencing preferences only.",
    "reasoning": "One-paragraph explanation of the outfit's strengths and weaknesses.",
    "why_it_works": "Short punchy sentence.",
    "what_to_improve": ["Quick win 1", "Quick win 2"]
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


def _normalize_analyze_output(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce common LLM quirks so the response validates against ScoredOutfit."""
    outfit = data.get("outfit")
    if not isinstance(outfit, dict):
        return data

    rec = outfit.get("recommendations")
    if not isinstance(rec, dict):
        outfit["recommendations"] = {
            "improvements": [],
            "issues": [],
            "styling_tips": [],
        }
    else:
        rec.setdefault("improvements", [])
        rec.setdefault("issues", [])
        rec.setdefault("styling_tips", [])

    def _match(val: Any, allowed: set[str]) -> str | None:
        if val is None:
            return None
        t = str(val).strip().title()
        if t == "Unkown":
            t = "Unknown"
        return t if t in allowed else None

    outfit["occasion_match"] = _match(outfit.get("occasion_match"), {"High", "Medium", "Low"})
    outfit["style_match"] = _match(outfit.get("style_match"), {"High", "Medium", "Low"})
    outfit["size_profile_match"] = _match(
        outfit.get("size_profile_match"),
        {"High", "Medium", "Low", "Unknown"},
    )

    fit_notes = str(outfit.get("fit_notes") or "")
    body_notes = str(outfit.get("body_profile_notes") or "")
    if body_notes and not fit_notes:
        outfit["fit_notes"] = body_notes
    elif fit_notes and not body_notes:
        outfit["body_profile_notes"] = fit_notes

    fc = outfit.get("fit_confidence")
    if fc is None and outfit.get("confidence") is not None:
        try:
            outfit["fit_confidence"] = int(round(float(outfit["confidence"]) * 100))
        except (TypeError, ValueError):
            outfit["fit_confidence"] = None
    elif fc is not None:
        try:
            outfit["fit_confidence"] = max(0, min(100, int(round(float(fc)))))
        except (TypeError, ValueError):
            outfit["fit_confidence"] = None

    if not outfit.get("why_it_works") and outfit.get("reasoning"):
        outfit["why_it_works"] = str(outfit["reasoning"])[:400]

    if not outfit.get("what_to_improve"):
        rec = outfit.get("recommendations") or {}
        if isinstance(rec, dict) and isinstance(rec.get("improvements"), list):
            outfit["what_to_improve"] = [str(x) for x in rec["improvements"][:6]]

    return data


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
    return _normalize_analyze_output({
        "outfit": {
            "items": _categorize_items(selected_items),
            "matching_score": 70,
            "confidence": 0.5,
            "fit_confidence": 50,
            "score_breakdown": {
                "color": 18, "occasion": 17, "fit": 14, "style": 10, "weather": 7, "preference": 4,
            },
            "occasion_match": "Medium",
            "style_match": "Medium",
            "size_profile_match": "Unknown",
            "recommendations": {
                "improvements": ["Review the color palette for better tonal harmony."],
                "issues": [],
                "styling_tips": ["Ensure the outfit matches the occasion you have in mind."],
            },
            "fit_notes": "We could not reach the AI scorer; this is a neutral placeholder.",
            "body_profile_notes": "We could not reach the AI scorer; this is a neutral placeholder.",
            "reasoning": "AI scoring is temporarily unavailable. This is a placeholder analysis — try again shortly.",
            "why_it_works": "Balanced basics — refine when AI is available.",
            "what_to_improve": ["Try again shortly for a personalised score."],
        },
        "missing_pieces": [],
        "style_tips": ["Complete your Style Profile for more personalised tips."],
    })


# ── Pairing suggestion prompt ──────────────────────────────────────────────────

_SUGGEST_PAIRINGS_PROMPT = """\
You are ClozeHive AI, an expert fashion stylist.

The user has already built an outfit (listed under "selected_outfit"). Your job is to scan their \
remaining closet items (listed under "remaining_closet") and suggest pieces that would COMPLEMENT or \
COMPLETE this specific outfit — not replace existing pieces, but genuinely ADD value to it.

RULES:
1. Only suggest items from the provided remaining_closet list. Use exact IDs and names.
2. Suggest 3–6 items maximum — only those that truly enhance the outfit.
3. Prioritise missing categories first (e.g. shoes if no footwear in outfit, outerwear if outfit has \
   no layer), then enhancing accessories, then optional layering pieces.
4. Reason must be specific (20–50 words): reference color harmony, style echo, occasion fit, or \
   fabric pairing — never generic phrases like "goes well with".
5. Return ONLY valid JSON — no markdown fences, no prose outside JSON.

EXACT RESPONSE SCHEMA:
{
  "suggested_pairings": [
    {
      "id": "uuid-of-item-from-remaining_closet",
      "reason": "Specific reason why this item enhances the outfit"
    }
  ]
}"""


# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_outfits(
    closet_items: list[dict[str, Any]],
    occasion: str,
    weather: str = "",
    temperature: float | None = None,
    user_profile: dict[str, Any] | None = None,
    rag_context: str | None = None,
) -> dict[str, Any]:
    """Generate 3 diverse, scored outfit combinations from the user's full wardrobe."""
    if not closet_items:
        return _mock_generate(closet_items, occasion)

    payload_dict: dict[str, Any] = {
        "mode": "generate",
        "occasion": occasion,
        "weather_condition": weather or "mild",
        "temperature_celsius": temperature,
        "user_profile": user_profile or {},
        "wardrobe": [_item_for_ai(i) for i in closet_items],
    }
    if rag_context:
        payload_dict["rag_context"] = rag_context
    payload = json.dumps(payload_dict, default=str)

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
    rag_context: str | None = None,
) -> dict[str, Any]:
    """Score and provide recommendations for a specific outfit combination chosen by the user."""
    if not selected_items:
        return _mock_analyze(selected_items, occasion)

    analyze_dict: dict[str, Any] = {
        "mode": "analyze",
        "occasion": occasion,
        "weather_condition": weather or "mild",
        "temperature_celsius": temperature,
        "user_profile": user_profile or {},
        "selected_outfit_items": [_item_for_ai(i) for i in selected_items],
    }
    if rag_context:
        analyze_dict["rag_context"] = rag_context
    payload = json.dumps(analyze_dict, default=str)

    try:
        raw = await ai_service.chat(
            [{"role": "user", "content": payload}],
            _ANALYZE_SYSTEM_PROMPT,
        )
        data = json.loads(_clean_json(raw))
        if isinstance(data, dict) and "outfit" in data:
            return _normalize_analyze_output(data)
    except json.JSONDecodeError:
        logger.warning("outfit_ai_analyze_bad_json", occasion=occasion)
    except Exception as exc:
        logger.warning("outfit_ai_analyze_failed", error=str(exc), occasion=occasion)

    return _mock_analyze(selected_items, occasion)


_SHUFFLE_OUTFIT_PROMPT = """\
You are ClozeHive AI, an expert fashion stylist.

The user has built an outfit with a specific match score. They want to try a DIFFERENT combination \
that might score higher or explore a different style direction.

Given the current outfit items and the user's full available closet, suggest 1-2 ALTERNATIVE outfit combinations.

RULES:
1. Use ONLY items from available_closet. Use exact IDs and names.
2. You may keep some items from current_outfit if they are strong anchors.
3. Each alternative should feel clearly different from the current outfit (different vibe, color story, or category emphasis).
4. If a "seed_category" is provided, make sure one alternative starts with an item of that category.
5. matching_score must equal color + occasion + fit + style + weather + preference (max 100).
6. Provide 2–3 specific improvement_tips explaining why this alternative scores better.
7. Return ONLY valid JSON — no markdown fences.

EXACT RESPONSE SCHEMA:
{
  "alternatives": [
    {
      "title": "Alternative outfit title",
      "items": [
        {"id": "uuid", "name": "...", "category": "...", "color": "..."}
      ],
      "matching_score": 91,
      "score_breakdown": {"color": 23, "occasion": 24, "fit": 19, "style": 13, "weather": 8, "preference": 4},
      "reasoning": "Why this combination works better or differently.",
      "improvement_tips": ["Specific tip 1", "Specific tip 2"],
      "fashion_rules_used": ["rule 1", "rule 2"]
    }
  ]
}"""


async def shuffle_outfit(
    current_items: list[dict[str, Any]],
    available_closet: list[dict[str, Any]],
    occasion: str,
    weather: str = "",
    seed_category: str | None = None,
) -> list[dict[str, Any]]:
    """Suggest 1-2 alternative outfit combinations from the user's closet.

    Returns a list of alternative outfit dicts (same shape as analyze response outfits).
    """
    if not available_closet:
        return []

    payload = json.dumps({
        "occasion": occasion,
        "weather": weather or "mild",
        "seed_category": seed_category or None,
        "current_outfit": [_item_for_ai(i) for i in current_items],
        "available_closet": [_item_for_ai(i) for i in available_closet[:50]],
    }, default=str)

    try:
        raw = await ai_service.chat(
            [{"role": "user", "content": payload}],
            _SHUFFLE_OUTFIT_PROMPT,
        )
        data = json.loads(_clean_json(raw))
        alternatives = data.get("alternatives")
        if isinstance(alternatives, list):
            return [a for a in alternatives if isinstance(a, dict) and a.get("items")]
    except json.JSONDecodeError:
        logger.warning("outfit_ai_shuffle_bad_json", occasion=occasion)
    except Exception as exc:
        logger.warning("outfit_ai_shuffle_failed", error=str(exc), occasion=occasion)

    return []


async def suggest_pairings_from_closet(
    selected_items: list[dict[str, Any]],
    remaining_items: list[dict[str, Any]],
    occasion: str,
    weather: str = "",
) -> list[dict[str, Any]]:
    """Ask the AI which remaining closet items would best complement the selected outfit.

    Returns a list of dicts with ``id`` and ``reason`` keys.  An empty list is
    returned on any error — callers must treat this as best-effort.
    """
    if not remaining_items:
        return []

    # Cap remaining items to keep the prompt size reasonable
    capped = remaining_items[:40]

    payload = json.dumps({
        "occasion": occasion,
        "weather": weather or "mild",
        "selected_outfit": [_item_for_ai(i) for i in selected_items],
        "remaining_closet": [_item_for_ai(i) for i in capped],
    }, default=str)

    try:
        raw = await ai_service.chat(
            [{"role": "user", "content": payload}],
            _SUGGEST_PAIRINGS_PROMPT,
        )
        data = json.loads(_clean_json(raw))
        pairings = data.get("suggested_pairings")
        if isinstance(pairings, list):
            return [p for p in pairings if isinstance(p, dict) and p.get("id")]
    except json.JSONDecodeError:
        logger.warning("outfit_ai_suggest_pairings_bad_json", occasion=occasion)
    except Exception as exc:
        logger.warning("outfit_ai_suggest_pairings_failed", error=str(exc), occasion=occasion)

    return []
