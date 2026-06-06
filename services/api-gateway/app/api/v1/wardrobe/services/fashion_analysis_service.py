"""
Fashion Analysis Agent  —  multi-item detection from a single image.

Design
------
One uploaded image may contain many distinct clothing items (shirt + jeans +
shoes + bag, or a flat-lay of an entire outfit).  This service:

1. Sends the image to OpenAI Vision with a structured prompt that asks for:
   • A list of every distinct wearable item
   • Approximate bounding boxes (as fractions 0-1 of the image dimensions)
   • Full fashion metadata per item (category, colors, material, occasions, …)

2. For each detected item:
   • Crops the image to the bounding box (with a small context margin)
   • Applies background removal (PIL-based, same as bulk_ingest pipeline)
   • Encodes the cropped RGBA PNG as base64 for direct API / storage use

3. Returns the structured JSON described in the API spec — ready for the
   closet database or a frontend review screen.

Why bounding-box crops instead of pixel segmentation
-----------------------------------------------------
We deliberately avoid heavy ML dependencies (SAM, Mask R-CNN, ONNX).
Bounding-box crops + PIL background removal handle ~80 % of wardrobe-photo
scenarios (flat-lays, studio shots, product images) well enough for a
wardrobe app.  Full segmentation can be swapped in later without changing
the calling contract.
"""

from __future__ import annotations

import base64
import io
import json
import math
import uuid
from typing import Any

from PIL import Image
from langsmith import traceable
from openai import APIError, AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.api.v1.wardrobe.services.background_removal_service import remove_background

settings = get_settings()
logger = get_logger("fashion_analysis_service")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        )
    return _client


def _build_name(raw: dict[str, Any]) -> str:
    """Build a human-friendly item name from vision metadata."""
    ai_name = raw.get("name")
    if ai_name and str(ai_name).lower() not in ("unknown", "null", "none", ""):
        return str(ai_name).strip()
    parts: list[str] = []
    color = raw.get("primary_color")
    if color and str(color).lower() not in ("unknown", "null", "none"):
        parts.append(str(color).title())
    sub = raw.get("subcategory") or raw.get("category") or "Item"
    parts.append(str(sub).title())
    return " ".join(parts) if parts else "Clothing Item"


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
        if "```" in text:
            text = text[: text.index("```")]
    return text.strip()


# ── Vision prompt ───────────────────────────────────────────────────────────────

_FASHION_PROMPT = """\
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


# ── Image processing helpers ────────────────────────────────────────────────────

_BBOX_MARGIN = 0.03   # 3 % context margin around each detected item


def _crop_item(image_bytes: bytes, bbox: dict[str, float]) -> bytes:
    """
    Crop the source image to the given bounding box (fractional coords) with a
    small context margin.  Returns PNG bytes of the cropped region.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        w, h = img.size

        x0 = max(0.0, bbox.get("x_min", 0.0) - _BBOX_MARGIN)
        y0 = max(0.0, bbox.get("y_min", 0.0) - _BBOX_MARGIN)
        x1 = min(1.0, bbox.get("x_max", 1.0) + _BBOX_MARGIN)
        y1 = min(1.0, bbox.get("y_max", 1.0) + _BBOX_MARGIN)

        left   = math.floor(x0 * w)
        top    = math.floor(y0 * h)
        right  = math.ceil(x1 * w)
        bottom = math.ceil(y1 * h)

        cropped = img.crop((left, top, right, bottom))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("crop_failed", error=str(exc))
        return image_bytes


def _to_base64_png(image_bytes: bytes) -> str:
    """Convert raw image bytes to a base64-encoded PNG data URL."""
    return base64.b64encode(image_bytes).decode("utf-8")


# ── Normalisation helpers ───────────────────────────────────────────────────────

_CATEGORY_ALIASES: dict[str, str] = {
    "top": "top", "tops": "top",
    "bottom": "bottom", "bottoms": "bottom",
    "shoe": "footwear", "shoes": "footwear",
    "sneakers": "footwear", "boots": "footwear",
    "accessory": "accessory", "accessories": "accessory",
    "bag": "accessory", "bags": "accessory",
    "hat": "accessory", "cap": "accessory",
    "outerwear": "outerwear", "jacket": "outerwear", "coat": "outerwear",
    "dress": "dress", "dresses": "dress",
    "other": "other",
}


def _norm_category(raw: Any) -> str:
    cat = str(raw or "other").strip().lower()
    return _CATEGORY_ALIASES.get(cat, "other")


def _norm_list(val: Any) -> list[str]:
    """Normalise an AI-returned list field to a deduplicated list of strings.

    Handles plain lists, comma-separated strings, and None/missing values.
    """
    if isinstance(val, list):
        items = [str(v).strip().lower() for v in val if v and str(v).strip()]
    elif isinstance(val, str):
        items = [s.strip().lower() for s in val.split(",") if s.strip()]
    else:
        return []
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]


def _norm_bbox(raw: Any) -> dict[str, float]:
    default = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
    if not isinstance(raw, dict):
        return default
    try:
        return {
            "x_min": float(raw.get("x_min", 0.0)),
            "y_min": float(raw.get("y_min", 0.0)),
            "x_max": float(raw.get("x_max", 1.0)),
            "y_max": float(raw.get("y_max", 1.0)),
        }
    except (TypeError, ValueError):
        return default


def _bbox_to_xywh_dict(bbox: dict[str, float]) -> dict[str, float]:
    xm = max(0.0, min(1.0, float(bbox.get("x_min", 0.0))))
    ym = max(0.0, min(1.0, float(bbox.get("y_min", 0.0))))
    xM = max(0.0, min(1.0, float(bbox.get("x_max", 1.0))))
    yM = max(0.0, min(1.0, float(bbox.get("y_max", 1.0))))
    return {"x": xm, "y": ym, "width": max(0.0, xM - xm), "height": max(0.0, yM - ym)}


def _safe_float(val: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return 0.0


# ── Fallback ────────────────────────────────────────────────────────────────────

def _fallback_item(reason: str) -> dict[str, Any]:
    full = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
    return {
        "item_id": str(uuid.uuid4())[:8],
        "category": "other",
        "subcategory": None,
        "gender": "unisex",
        "fit": None,
        "sleeve_type": None,
        "primary_color": None,
        "secondary_color": None,
        "pattern": None,
        "material": None,
        "brand": None,
        "occasions": [],
        "season": [],
        "style_tags": [],
        "description": f"AI analysis unavailable: {reason}",
        "image_base64": None,
        "detection_confidence": 0.0,
        "segmentation_quality": "low",
        "bbox": full,
        "bounding_box": _bbox_to_xywh_dict(full),
    }


# ── Detection-only (used by vision pipeline — avoids duplicate OpenAI + enrich) ─

@traceable(name="gateway_fashion_detect_items", run_type="chain")
async def detect_fashion_items(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
) -> dict[str, Any]:
    """
    Multi-item detection via OpenAI vision. Normalizes bbox per item.
    Does not crop, remove background, or call per-item refine (vision pipeline does that).
    """
    if not settings.openai_api_key:
        reason = "No OPENAI_API_KEY configured"
        logger.warning("fashion_detection_skipped", reason=reason)
        return {"total_items_detected": 1, "items": [_fallback_item(reason)]}

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{image_b64}"

    try:
        response = await _get_client().chat.completions.create(
            model=settings.openai_model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                        {"type": "text", "text": _FASHION_PROMPT},
                    ],
                }
            ],
        )
        raw_text = (response.choices[0].message.content or "").strip()
        vision_data: dict[str, Any] = json.loads(_clean_json(raw_text))
    except (APIError, json.JSONDecodeError, Exception) as exc:
        logger.error("fashion_vision_failed", error=str(exc))
        return {"total_items_detected": 1, "items": [_fallback_item(str(exc))]}

    raw_items = vision_data.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        logger.warning("fashion_no_items_detected")
        return {"total_items_detected": 0, "items": []}

    for raw in raw_items:
        if isinstance(raw, dict):
            bbox = _norm_bbox(raw.get("bbox"))
            raw["bbox"] = bbox
            raw["bounding_box"] = _bbox_to_xywh_dict(bbox)

    return {
        "total_items_detected": len(raw_items),
        "items": raw_items,
    }


# ── Main public function ────────────────────────────────────────────────────────

@traceable(name="gateway_fashion_analyze_image", run_type="chain")
async def analyze_fashion_image(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
) -> dict[str, Any]:
    """
    Detect all fashion items in a single image.

    Returns a dict matching the CLOZEHIVE Fashion Analysis Agent JSON spec:
    {
      "total_items_detected": N,
      "items": [ { item_id, category, …, image_base64, detection_confidence, … } ]
    }

    Never raises — all failures produce a single fallback item so the API
    always returns a parseable response.
    """
    det = await detect_fashion_items(image_bytes, media_type)
    raw_items = det.get("items") or []
    if not raw_items:
        return det

    # ── Per item: crop → BG removal → per-crop metadata refinement ─────────────
    processed_items: list[dict[str, Any]] = []

    from app.api.v1.wardrobe.services.item_vision_enrichment import enrich_detection_with_crop_analysis

    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue

        item_id = raw.get("item_id") or f"item_{idx + 1:03d}"
        bbox = _norm_bbox(raw.get("bbox"))

        try:
            crop_bytes = _crop_item(image_bytes, bbox)
            final_bytes = remove_background(crop_bytes)
            image_b64_str = _to_base64_png(final_bytes)
        except Exception as exc:
            logger.warning("fashion_item_image_failed", item_id=item_id, error=str(exc))
            image_b64_str = _to_base64_png(image_bytes)
            final_bytes = base64.b64decode(image_b64_str)

        det_payload: dict[str, Any] = {
            "item_id": item_id,
            "category": _norm_category(raw.get("category")),
            "subcategory": raw.get("subcategory") or None,
            "gender": raw.get("gender") or "unisex",
            "fit": raw.get("fit") or None,
            "sleeve_type": raw.get("sleeve_type") or None,
            "primary_color": raw.get("primary_color") or None,
            "secondary_color": raw.get("secondary_color") or None,
            "pattern": raw.get("pattern") or None,
            "material": raw.get("material") or None,
            "brand": raw.get("brand") or None,
            "occasions": _norm_list(raw.get("occasions")),
            "season": _norm_list(raw.get("season")),
            "style_tags": _norm_list(raw.get("style_tags")),
            "description": raw.get("description") or None,
            "detection_confidence": _safe_float(raw.get("detection_confidence")),
            "segmentation_quality": raw.get("segmentation_quality") or "medium",
            "bbox": bbox,
        }
        enriched = await enrich_detection_with_crop_analysis(final_bytes, det_payload)

        item_out: dict[str, Any] = {
            "item_id": item_id,
            "category": enriched.get("category") or _norm_category(raw.get("category")),
            "subcategory": enriched.get("subcategory") or raw.get("subcategory") or None,
            "gender": enriched.get("gender") or raw.get("gender") or "unisex",
            "fit": enriched.get("fit") or raw.get("fit") or None,
            "sleeve_type": enriched.get("sleeve_type") or raw.get("sleeve_type") or None,
            "primary_color": enriched.get("primary_color") or raw.get("primary_color") or None,
            "secondary_color": enriched.get("secondary_color") or raw.get("secondary_color") or None,
            "pattern": enriched.get("pattern") or raw.get("pattern") or None,
            "material": enriched.get("material") or raw.get("material") or None,
            "brand": enriched.get("brand") or raw.get("brand") or None,
            "occasions": enriched.get("occasions") if enriched.get("occasions") else _norm_list(raw.get("occasions")),
            "season": enriched.get("season") if enriched.get("season") else _norm_list(raw.get("season")),
            "style_tags": enriched.get("style_tags") if enriched.get("style_tags") else _norm_list(raw.get("style_tags")),
            "description": enriched.get("description") or raw.get("description") or None,
            "bbox": bbox,
            "bounding_box": _bbox_to_xywh_dict(bbox),
            "image_base64": image_b64_str,
            "detection_confidence": float(enriched.get("detection_confidence") or _safe_float(raw.get("detection_confidence"))),
            "segmentation_quality": raw.get("segmentation_quality") or "medium",
        }
        item_out["name"] = _build_name({**enriched, "name": enriched.get("name") or raw.get("name")})
        processed_items.append(item_out)

    logger.info(
        "fashion_analysis_complete",
        total_detected=len(processed_items),
    )

    return {
        "total_items_detected": len(processed_items),
        "items": processed_items,
    }
