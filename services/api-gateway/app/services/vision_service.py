"""Consolidated vision service for garment image analysis."""

from __future__ import annotations

import base64
import json

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("vision_service")

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
        if "```" in text:
            text = text[: text.index("```")]
    return text.strip()


def _fallback(reason: str) -> dict:
    logger.warning("vision_fallback", reason=reason)
    return {
        "name": "Unknown Clothing Item",
        "category": "tops",
        "color": "Unknown",
        "brand": "",
        "material": "",
        "pattern": "",
        "occasion": ["casual"],
        "tags": [],
        "eco_score": None,
        "confidence": 0.0,
        "notes": f"Auto-analysis unavailable ({reason}). Please fill in details manually.",
    }


def _bulk_fallback(reason: str) -> dict:
    logger.warning("bulk_vision_fallback", reason=reason)
    return {
        "name": "Clothing Item",
        "category": "tops",
        "subcategory": "Unknown",
        "description": "AI analysis unavailable. Please fill in details manually.",
        "primary_color": "Unknown",
        "secondary_colors": [],
        "pattern": "Unknown",
        "material": "Unknown",
        "occasion_tags": ["Casual"],
        "season_tags": [],
        "style_tags": [],
        "fit": "Regular",
        "eco_score": None,
        "brand": "",
        "confidence_score": 0.0,
        "warnings": [f"Auto-analysis unavailable: {reason}"],
    }


# ── Standard single-item analysis (used by /upload, /bulk-upload) ─────────────

async def analyze_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    if not settings.anthropic_api_key:
        return _fallback("ANTHROPIC_API_KEY not set")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "Analyse this clothing item and return ONLY valid JSON with fields: "
        "name, category (tops, bottoms, shoes, outerwear, dresses, accessories, other), "
        "color, brand, material, pattern, occasion array, tags array, eco_score, confidence, notes."
    )
    try:
        response = await _get_client().messages.create(
            model=settings.anthropic_model,
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
        return json.loads(_clean_json(text))
    except (anthropic.APIError, json.JSONDecodeError, Exception) as exc:
        logger.error("vision_analysis_failed", error=str(exc))
        return _fallback(str(exc))


# ── Rich bulk-ingestion analysis (used by /smart-ingest pipeline) ─────────────

_BULK_PROMPT = """\
Analyse this clothing item image and return ONLY valid JSON with these exact fields.
Be precise; do not hallucinate brand names unless a logo is clearly visible.

{
  "name": "Descriptive item name (e.g. White Slim-Fit Oxford Shirt)",
  "category": "tops | bottoms | shoes | outerwear | dresses | accessories | other",
  "subcategory": "e.g. T-Shirt | Jeans | Sneakers | Blazer | Maxi Dress | Belt",
  "description": "2-3 sentence plain-English description suitable for a wardrobe app",
  "primary_color": "Single dominant color name",
  "secondary_colors": ["list", "of", "accent", "colors"],
  "pattern": "Solid | Striped | Plaid | Floral | Graphic | Animal Print | Tie-Dye | Camo | Other",
  "material": "Primary fabric e.g. Cotton, Denim, Polyester, Silk, Wool, Linen",
  "occasion_tags": ["Casual", "Business Casual", "Formal", "Sport", "Beach", "Date Night", "Travel"],
  "season_tags": ["Spring", "Summer", "Fall", "Winter"],
  "style_tags": ["Minimal", "Streetwear", "Classic", "Bohemian", "Preppy", "Sporty", "Elegant", "Vintage"],
  "fit": "Slim | Regular | Relaxed | Oversized | Tailored",
  "eco_score": null or 0-10 float,
  "brand": "Brand name if logo is clearly visible, else empty string",
  "confidence_score": 0.0-1.0 float reflecting detection certainty
}

Return ONLY valid JSON. No markdown fences, no prose."""


async def analyze_for_bulk(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Rich garment analysis for the smart-ingest pipeline.

    Returns an expanded schema (subcategory, secondary_colors, season_tags,
    style_tags, fit, description) compared to the basic analyze_image().

    Why separate function: avoids changing the existing analyze_image() contract
    which other endpoints depend on. Extension over modification.
    """
    if not settings.anthropic_api_key:
        return _bulk_fallback("ANTHROPIC_API_KEY not set")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        response = await _get_client().messages.create(
            model=settings.anthropic_model,
            max_tokens=1200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": _BULK_PROMPT},
                ],
            }],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        data = json.loads(_clean_json(text))
        if not isinstance(data, dict):
            raise ValueError("Response is not a JSON object")
        return data
    except (anthropic.APIError, json.JSONDecodeError, Exception) as exc:
        logger.error("bulk_vision_analysis_failed", error=str(exc))
        return _bulk_fallback(str(exc))
