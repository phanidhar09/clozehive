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
import time
import uuid
from typing import Any

from langsmith import traceable
from openai import APIError, AsyncOpenAI
from PIL import Image

from app.api.v1.wardrobe.services.background_removal_service import remove_background
from app.api.v1.wardrobe.services.fashion_detection_prompt import FASHION_DETECTION_PROMPT
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client

settings = get_settings()
logger = get_logger("fashion_analysis_service")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = wrap_openai_client(make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url))
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


# The detection prompt lives in fashion_detection_prompt (shared with the Gemini path).


# ── Image processing helpers ────────────────────────────────────────────────────

_BBOX_MARGIN = 0.03  # 3 % context margin around each detected item


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

        left = math.floor(x0 * w)
        top = math.floor(y0 * h)
        right = math.ceil(x1 * w)
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
    "top": "top",
    "tops": "top",
    "bottom": "bottom",
    "bottoms": "bottom",
    "shoe": "footwear",
    "shoes": "footwear",
    "sneakers": "footwear",
    "boots": "footwear",
    "accessory": "accessory",
    "accessories": "accessory",
    "bag": "accessory",
    "bags": "accessory",
    "hat": "accessory",
    "cap": "accessory",
    "outerwear": "outerwear",
    "jacket": "outerwear",
    "coat": "outerwear",
    "dress": "dress",
    "dresses": "dress",
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

    # Token/cost capture reuses the vision_service helper (same $ai_generation
    # plumbing as the chat path).
    from app.api.v1.wardrobe.services.vision_service import _capture_vision_generation

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": settings.vision_detection_detail},
                },
                {"type": "text", "text": FASHION_DETECTION_PROMPT},
            ],
        }
    ]
    started = time.perf_counter()
    try:
        response = await _get_client().chat.completions.create(  # type: ignore[call-overload]
            # Detection tier: bounding boxes + rough classification only — the
            # per-item enrichment pass (analyze_for_bulk) refines attributes on
            # the flagship model. Detail stays high for bbox precision.
            model=settings.vision_detection_model,
            max_tokens=4096,
            # JSON mode — guarantees a parseable object, no markdown fences to strip.
            response_format={"type": "json_object"},
            messages=messages,
        )
        raw_text = (response.choices[0].message.content or "").strip()
        _capture_vision_generation(
            model=settings.vision_detection_model,
            messages=messages,
            output_text=raw_text,
            usage=getattr(response, "usage", None),
            elapsed=time.perf_counter() - started,
            operation="vision_detection",
            telemetry=None,
        )
        vision_data: dict[str, Any] = json.loads(_clean_json(raw_text))
    except (APIError, json.JSONDecodeError, Exception) as exc:
        logger.error("fashion_vision_failed", error=str(exc))
        _capture_vision_generation(
            model=settings.vision_detection_model,
            messages=messages,
            output_text="",
            usage=None,
            elapsed=time.perf_counter() - started,
            operation="vision_detection",
            telemetry=None,
            is_error=True,
        )
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
            "style_tags": enriched.get("style_tags")
            if enriched.get("style_tags")
            else _norm_list(raw.get("style_tags")),
            "description": enriched.get("description") or raw.get("description") or None,
            "bbox": bbox,
            "bounding_box": _bbox_to_xywh_dict(bbox),
            "image_base64": image_b64_str,
            "detection_confidence": float(
                enriched.get("detection_confidence") or _safe_float(raw.get("detection_confidence"))
            ),
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
