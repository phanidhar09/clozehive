"""
Gemini Vision Service — clothing detection + metadata via Gemini 1.5 Flash.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langsmith import traceable

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("gemini_service")

# ── Lazy model singleton ──────────────────────────────────────────────────────

_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        import google.generativeai as genai  # type: ignore[import]

        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        logger.info("gemini_model_initialized", model=settings.gemini_model)
    return _model


# ── Detection prompt ──────────────────────────────────────────────────────────

_DETECTION_PROMPT = """\
You are an expert fashion AI specializing in multi-item clothing detection.

TASK: Detect EVERY distinct wearable item visible in this image. Each item becomes \
an independent closet entry — treat each one with the same thoroughness as if it \
were the only item in the photo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO DETECT (include ALL of these):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• tops: t-shirt, shirt, blouse, tank top, hoodie, sweater, cardigan, crop top
• bottoms: jeans, trousers, shorts, skirt, leggings, joggers
• outerwear: jacket, coat, blazer, parka, vest, windbreaker
• footwear: sneakers, boots, shoes, sandals, heels, loafers
• accessories: bag, handbag, backpack, hat, cap, belt, scarf, watch, sunglasses
• full-body: dress, jumpsuit, romper, suit

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY MULTI-ITEM RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ONE garment = ONE array entry. NEVER merge.
   ✓ Shirt + jeans + sneakers → 3 entries
   ✓ Flat-lay with 5 items → 5 entries
   ✓ Single hoodie → 1 entry

2. FLAT-LAY images: every garment arranged on a surface gets its own tight bbox \
   covering only that garment. Do NOT use one large bbox for the whole layout.

3. OVERLAPPING layers: jacket worn over shirt → 2 entries with overlapping bboxes.

4. PARTIAL visibility: include items that are >10% visible. Mark as segmentation_quality "low".

5. SMALL items: accessories like belts, watches, and sunglasses must each get \
   their own entry even if small relative to the frame.

6. NEVER stop at the first item — scan the ENTIRE image systematically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BBOX RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Fractional coords, (0,0)=top-left, (1,1)=bottom-right.
• Tight around the visible region of THAT item only.
• Never use {x_min:0, y_min:0, x_max:1, y_max:1} unless item truly fills the frame.
• Minimum bbox area: (x_max-x_min) × (y_max-y_min) ≥ 0.005 of the image.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
METADATA RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• detection_confidence: 0.0–1.0 per item.
• Only output items with detection_confidence ≥ 0.35.
• segmentation_quality: "high", "medium", or "low".
• brand: null unless logo/text is CLEARLY and FULLY readable.
• Use null (not "") for truly unknown fields.

Return ONLY valid JSON — no markdown, no prose, no trailing commas:

{
  "total_items_detected": <integer>,
  "items": [
    {
      "item_id": "item_001",
      "category": "top | bottom | footwear | outerwear | accessory | dress | other",
      "subcategory": "<specific type e.g. t-shirt, slim jeans, white sneakers>",
      "name": "<descriptive name e.g. Navy Slim-Fit Jeans>",
      "description": "<one-sentence plain-English description>",
      "gender": "male | female | unisex",
      "fit": "slim | regular | oversized | relaxed | tailored | null",
      "sleeve_type": "long | short | sleeveless | null",
      "primary_color": "<specific color name>",
      "secondary_color": "<color name or null>",
      "pattern": "solid | striped | checked | graphic | floral | animal_print | tie_dye | camo | null",
      "material": "cotton | denim | leather | polyester | silk | wool | linen | synthetic | unknown | null",
      "brand": "<brand name or null>",
      "occasions": ["casual","formal","business","party","travel","gym"],
      "season": ["summer","winter","all-season","fall","spring"],
      "style_tags": ["minimal","streetwear","sporty","elegant","vintage","classic","preppy","bohemian"],
      "bbox": {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0},
      "detection_confidence": 0.95,
      "segmentation_quality": "high"
    }
  ]
}

REMINDER: Return ALL items. A flat-lay of 5 clothes = 5 entries. \
An outfit photo (shirt + jeans + shoes) = 3 entries minimum."""


# ── JSON cleaning ─────────────────────────────────────────────────────────────

def _clean_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


# ── Public API ────────────────────────────────────────────────────────────────

def is_available() -> bool:
    """True only when GEMINI_API_KEY looks like a real developer key."""
    k = settings.gemini_api_key.strip()
    if len(k) < 24:
        return False
    low = k.lower().replace("-", "").replace("_", "")
    if "yourgeminiapikey" in low or "yourgeminikey" in low:
        return False
    if "placeholder" in low or low.startswith("replace"):
        return False
    return True


@traceable(name="gemini_detect_and_classify", run_type="llm")
async def detect_and_classify(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    """
    Send image to Gemini 1.5 Flash for combined detection + metadata.
    """
    model = _get_model()

    effective_mime = media_type if media_type in (
        "image/jpeg", "image/png", "image/webp", "image/gif"
    ) else "image/jpeg"

    image_part = {"mime_type": effective_mime, "data": image_bytes}

    try:
        response = await model.generate_content_async(
            [_DETECTION_PROMPT, image_part]
        )
        raw_text = response.text.strip()
    except Exception as exc:
        logger.error("gemini_api_error", error=str(exc))
        raise

    try:
        result: dict[str, Any] = json.loads(_clean_json(raw_text))
    except json.JSONDecodeError as exc:
        logger.error("gemini_json_parse_error", error=str(exc), preview=raw_text[:400])
        raise ValueError(f"Gemini returned invalid JSON: {exc}") from exc

    items: list[dict[str, Any]] = result.get("items") or []

    for idx, item in enumerate(items):
        if not item.get("item_id"):
            item["item_id"] = f"item_{idx + 1:03d}"
        for field in ("occasions", "season", "style_tags"):
            if not isinstance(item.get(field), list):
                item[field] = []
        bbox = item.get("bbox")
        if not isinstance(bbox, dict):
            item["bbox"] = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
        else:
            if "x" in bbox and "x_min" not in bbox:
                item["bbox"] = {
                    "x_min": float(bbox.get("x", 0)),
                    "y_min": float(bbox.get("y", 0)),
                    "x_max": float(bbox.get("x", 0)) + float(bbox.get("width", 1)),
                    "y_max": float(bbox.get("y", 0)) + float(bbox.get("height", 1)),
                }
        item.setdefault("detection_confidence", item.pop("confidence_score", 0.8))
        item.setdefault("segmentation_quality", "medium")

    logger.info("gemini_detection_complete", items=len(items))
    return {"total_items_detected": len(items), "items": items}
