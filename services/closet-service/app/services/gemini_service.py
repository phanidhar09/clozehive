"""
Gemini Vision Service — clothing detection + metadata via Gemini 1.5 Flash.

One API call returns ALL detected items with bounding boxes AND full fashion
metadata.  Gemini 1.5 Flash is ~3–5× faster than GPT-4o for this task.

Fallback: if GEMINI_API_KEY is not set the caller should use the existing
OpenAI-based fashion_analysis_service instead.

NOTE: This file is shared verbatim between closet-service and vision-service
(see scripts/check_service_drift.py). Edit both copies — CI fails on drift.

Return shape (same contract as fashion_analysis_service.analyze_fashion_image):
  {
    "total_items_detected": int,
    "items": [
      {
        "item_id":         str,      # "item_001", "item_002", …
        "category":        str,      # top/bottom/footwear/outerwear/accessory/dress/other
        "subcategory":     str|null,
        "name":            str,
        "description":     str|null,
        "gender":          str,      # male/female/unisex
        "fit":             str|null,
        "sleeve_type":     str|null,
        "primary_color":   str|null,
        "secondary_color": str|null,
        "pattern":         str|null,
        "material":        str|null,
        "brand":           str|null,
        "occasions":       list[str],
        "season":          list[str],
        "style_tags":      list[str],
        "bbox":            {"x_min", "y_min", "x_max", "y_max"},  # fractions 0–1
        "detection_confidence": float,
        "segmentation_quality": str,   # high/medium/low
      }
    ]
  }
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

# ── Lazy client singleton (google-genai SDK) ──────────────────────────────────

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from google import genai  # type: ignore[import]

        _client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("gemini_client_initialized", model=settings.gemini_model)
    return _client


# ── Detection prompt ──────────────────────────────────────────────────────────

_DETECTION_PROMPT = """\
You are an expert fashion AI with deep knowledge of garment construction, fabric, \
color theory, and wardrobe cataloguing.

TASK: Detect EVERY distinct wearable item visible in this image. Each item becomes \
an independent closet entry — analyse each with the same care as if it were the \
only item in the photo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO DETECT (include ALL of these):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• tops: t-shirt, shirt, blouse, tank top, hoodie, sweatshirt, sweater, cardigan, crop top
• bottoms: jeans, trousers, chinos, shorts, skirt, leggings, joggers, cargo pants
• outerwear: jacket, coat, blazer, parka, windbreaker, trench coat, bomber jacket
• footwear: sneakers, boots, shoes, oxfords, loafers, sandals, heels, slides
• accessories: bag, handbag, backpack, tote, hat, cap, belt, scarf, watch, sunglasses, jewelry
• full-body: dress, jumpsuit, romper, suit, co-ord set

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MULTI-ITEM RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ONE garment = ONE array entry. NEVER merge.
   ✓ Shirt + jeans + sneakers → 3 entries
   ✓ Flat-lay with 5 items → 5 entries
2. FLAT-LAY: every garment gets its own tight bbox — do NOT use one bbox for the whole layout.
3. LAYERED OUTFITS: jacket over shirt → 2 entries, each with its own tight bbox.
4. PARTIAL items >10% visible → include, set segmentation_quality "low".
5. SMALL accessories: belt, watch, sunglasses each get their own entry.
6. Scan ENTIRE image — top-to-bottom, left-to-right — before writing any item.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BBOX RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Fractional coords, (0,0)=top-left, (1,1)=bottom-right.
• Tight around the visible region of THAT item only.
• Never use {x_min:0, y_min:0, x_max:1, y_max:1} unless item truly fills the frame.
• Minimum bbox area: (x_max-x_min)×(y_max-y_min) ≥ 0.005.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLOR — BE SPECIFIC:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use precise color names. Prefer:
  navy blue, cobalt blue, sky blue, powder blue, teal, turquoise
  forest green, olive green, sage green, mint green, emerald
  crimson, burgundy, coral, salmon, blush pink, hot pink, magenta
  charcoal, slate grey, silver, light grey, off-white, ivory, cream
  camel, tan, khaki, beige, sand, rust, burnt orange, mustard
  black, white — only if truly pure.
Avoid vague terms like "blue", "green", "gray". Pick the most accurate specific shade.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATERIAL — READ THE FABRIC, NOT THE COLOR:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Look at visible texture and drape:
  • Matte flat weave, slight texture → cotton or linen
  • Diagonal twill pattern, rigid body → denim
  • Shiny, fluid, drapes in liquid folds → silk or satin
  • Fuzzy surface, warm visual weight → wool or fleece
  • Fine ribbing or tight knit → knit / knitwear
  • Smooth high-sheen, plastic-looking → polyester or synthetic
  • Grained or smooth stiff surface with sheen → leather or faux-leather
  • Porous open weave → linen or woven cotton
If texture is not determinable from the image, output "unknown" — never guess.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CATEGORY EDGE CASES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• hoodie, sweatshirt, cardigan → top (not outerwear)
• blazer worn as outermost layer → outerwear
• vest worn as outermost layer → outerwear; vest worn under jacket → do not detect separately
• bodysuit worn as top → top
• leggings → bottom; tights worn with dress → do not detect separately

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OTHER METADATA RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• detection_confidence: 0.0–1.0 (visibility × identification certainty). Min 0.35 to include.
• segmentation_quality: "high" (clean edges), "medium" (some occlusion), "low" (heavily occluded).
• brand: null unless a logo or text label is CLEARLY and FULLY legible. Never guess a brand.
• Use null (not "") for all unknown/unverifiable fields.
• name: format as "<Color> <Subcategory>" e.g. "Navy Slim-Fit Jeans", "Ivory Cable-Knit Sweater".
• description: one concrete sentence — mention the actual item's visible qualities, not generics.

Return ONLY valid JSON — no markdown, no prose, no trailing commas:

{
  "total_items_detected": <integer>,
  "items": [
    {
      "item_id": "item_001",
      "category": "top | bottom | footwear | outerwear | accessory | dress | other",
      "subcategory": "<specific e.g. slim jeans | oversized hoodie | white leather sneakers>",
      "name": "<Color Subcategory e.g. Charcoal Slim-Fit Chinos>",
      "description": "<one specific sentence about this item's visible qualities>",
      "gender": "male | female | unisex",
      "fit": "slim | regular | oversized | relaxed | tailored | null",
      "sleeve_type": "long | short | sleeveless | null",
      "primary_color": "<specific shade e.g. navy blue | charcoal | ivory>",
      "secondary_color": "<specific shade or null>",
      "pattern": "solid | striped | plaid | checked | graphic | floral | animal_print | tie_dye | camo | houndstooth | paisley | null",
      "material": "cotton | denim | leather | faux-leather | polyester | silk | wool | linen | fleece | knit | synthetic | unknown",
      "brand": "<brand name or null>",
      "occasions": ["casual","formal","business","party","travel","gym","beach","date"],
      "season": ["summer","winter","all-season","fall","spring"],
      "style_tags": ["minimal","streetwear","sporty","elegant","vintage","classic","preppy","bohemian","athleisure","workwear"],
      "bbox": {"x_min": 0.05, "y_min": 0.10, "x_max": 0.95, "y_max": 0.90},
      "detection_confidence": 0.95,
      "segmentation_quality": "high | medium | low"
    }
  ]
}

BEFORE SUBMITTING: re-read your output and verify each item has the tightest possible \
bbox, the most specific color name, and a material that matches the visible texture."""


# ── JSON cleaning ─────────────────────────────────────────────────────────────

def _clean_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


# ── Public API ────────────────────────────────────────────────────────────────

def is_available() -> bool:
    """True only when GEMINI_API_KEY looks like a real developer key (.env placeholders skipped)."""
    k = settings.gemini_api_key.strip()
    if len(k) < 24:
        return False
    low = k.lower().replace("-", "").replace("_", "")
    # Copy-paste artefacts from `.env.example`
    if "yourgeminiapikey" in low or "yourgeminikey" in low:
        return False
    if "placeholder" in low or low.startswith("replace"):
        return False
    return True


@traceable(name="gemini_detect_and_classify", run_type="llm")
async def detect_and_classify(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    """
    Send image to Gemini 1.5 Flash for combined detection + metadata.

    Returns the standard detection dict (same shape as fashion_analysis_service).
    Raises on API error or JSON parse failure — callers should catch and fall back.
    """
    from google.genai import types  # type: ignore[import]

    client = _get_client()

    # Gemini accepts inline image bytes
    effective_mime = media_type if media_type in (
        "image/jpeg", "image/png", "image/webp", "image/gif"
    ) else "image/jpeg"

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=effective_mime),
                _DETECTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
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
        # Ensure item_id
        if not item.get("item_id"):
            item["item_id"] = f"item_{idx + 1:03d}"
        # Ensure list fields are lists
        for field in ("occasions", "season", "style_tags"):
            if not isinstance(item.get(field), list):
                item[field] = []
        # Ensure bbox dict
        bbox = item.get("bbox")
        if not isinstance(bbox, dict):
            item["bbox"] = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
        else:
            # Normalise keys — Gemini sometimes returns x/y instead of x_min/y_min
            if "x" in bbox and "x_min" not in bbox:
                item["bbox"] = {
                    "x_min": float(bbox.get("x", 0)),
                    "y_min": float(bbox.get("y", 0)),
                    "x_max": float(bbox.get("x", 0)) + float(bbox.get("width", 1)),
                    "y_max": float(bbox.get("y", 0)) + float(bbox.get("height", 1)),
                }
        # Normalise confidence
        item.setdefault("detection_confidence", item.pop("confidence_score", 0.8))
        item.setdefault("segmentation_quality", "medium")

    # ── Server-side quality gates ─────────────────────────────────────────────

    # 1. Filter items below the confidence threshold (prompt says ≥0.35; enforce here)
    before_conf = len(items)
    items = [i for i in items if float(i.get("detection_confidence", 0)) >= 0.35]
    if len(items) < before_conf:
        logger.info("gemini_low_confidence_filtered", removed=before_conf - len(items))

    # 2. Validate and repair bounding box dimensions
    for item in items:
        bbox = item["bbox"]
        x_min = max(0.0, min(float(bbox.get("x_min", 0)), 1.0))
        y_min = max(0.0, min(float(bbox.get("y_min", 0)), 1.0))
        x_max = max(0.0, min(float(bbox.get("x_max", 1)), 1.0))
        y_max = max(0.0, min(float(bbox.get("y_max", 1)), 1.0))
        area = (x_max - x_min) * (y_max - y_min)
        if area < 0.001:
            # Degenerate bbox — reset to full frame and mark quality low
            item["bbox"] = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
            item["segmentation_quality"] = "low"
            logger.warning("gemini_degenerate_bbox_repaired", item_id=item.get("item_id"), area=area)
        else:
            item["bbox"] = {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max}

    # 3. Deduplicate: drop near-identical items (same category + overlapping bbox)
    items = _deduplicate_items(items)

    # Re-sequence item_ids after filtering
    for idx, item in enumerate(items):
        item["item_id"] = f"item_{idx + 1:03d}"

    logger.info("gemini_detection_complete", items=len(items))
    return {"total_items_detected": len(items), "items": items}


def _bbox_iou(a: dict, b: dict) -> float:
    """Intersection-over-Union for two fractional bounding boxes."""
    ix1 = max(a["x_min"], b["x_min"])
    iy1 = max(a["y_min"], b["y_min"])
    ix2 = min(a["x_max"], b["x_max"])
    iy2 = min(a["y_max"], b["y_max"])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = (a["x_max"] - a["x_min"]) * (a["y_max"] - a["y_min"])
    area_b = (b["x_max"] - b["x_min"]) * (b["y_max"] - b["y_min"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _deduplicate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate detections: same category + heavily overlapping bbox (IoU ≥ 0.80).

    When two items overlap that much and share a category, keep the one with
    the higher detection_confidence.
    """
    kept: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda i: float(i.get("detection_confidence", 0)), reverse=True):
        is_dup = False
        for existing in kept:
            if existing.get("category") == item.get("category"):
                iou = _bbox_iou(existing["bbox"], item["bbox"])
                if iou >= 0.80:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(item)
    if len(kept) < len(items):
        logger.info("gemini_duplicates_removed", removed=len(items) - len(kept))
    return kept
