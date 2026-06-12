"""
Vision Pipeline Service — optimized multi-item detection with BG removal.

Two public entry points
-----------------------
run_pipeline()           — batch (returns VisionAnalyzeResponse when complete)
run_pipeline_streaming() — async generator yielding SSE-formatted strings

Streaming pipeline stages
--------------------------
1. Compress     — Resize to ≤1024 px, quality 85 %, strip EXIF.
2. Cache check  — SHA-256 → Redis (1 h TTL).
3. Detection    — Gemini 1.5 Flash (primary) → GPT-4o fallback (≤30 s).
                  Streams `items_detected` event immediately after completion.
4. BG removal   — asyncio tasks per item; each streams `item_ready` as it finishes.
                  Parallel processing keeps total BG time ≈ worst single-item time.
5. Cache write  — Save metadata (no images) to Redis.
6. Complete     — Streams `complete` event with timing.

Performance (Gemini 1.5 Flash, 3-item image)
--------------------------------------------
• No cache: ~2–5 s perceived (detection 1–3 s + BG streams progressively)
• Cache hit: <200 ms (BG still runs on crops but detection skipped)
• 10-item image: ~3–6 s (BG parallel, user sees items appearing one by one)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import math
import time
from typing import Any, cast
from uuid import uuid4

from PIL import Image

from app.api.v1.wardrobe.schemas.closet import NormalizedBoundingBox, VisionAnalysisItem, VisionAnalyzeResponse
from app.api.v1.wardrobe.services import fashion_analysis_service
from app.api.v1.wardrobe.services.background_removal_service import remove_background_async
from app.api.v1.wardrobe.services.fashion_analysis_service import _bbox_to_xywh_dict
from app.api.v1.wardrobe.services.item_vision_enrichment import enrich_detection_with_crop_analysis
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("vision_pipeline")

# ── Tuning constants ───────────────────────────────────────────────────────────

_MAX_DIMENSION = 1500  # px — resize larger images before sending to AI
_MAX_DIMENSION_PREVIEW_FAST = 1120  # smaller image → faster detection for closet preview-only path
_JPEG_QUALITY = 85  # JPEG quality for compressed version sent to AI
_JPEG_QUALITY_FAST = 82  # preview_fast per-item thumbnails
_CACHE_TTL = 3_600  # 1 hour (Redis seconds)
_VISION_TIMEOUT = 45.0  # seconds — OpenAI Vision call
_BG_TIMEOUT = 30.0  # seconds — per-item BG removal
_CACHE_KEY_PFX = "vision_pipeline:v3:"

# Multi-item deduplication thresholds
_IOU_DEDUP_THRESHOLD = 0.70  # merge/drop bbox if IOU exceeds this
_MIN_BBOX_AREA = 0.003  # drop items whose bbox covers < 0.3% of image
_MIN_CONFIDENCE = 0.35  # drop items below this detection confidence

# ── Image compression ──────────────────────────────────────────────────────────


def _compress_image(
    image_bytes: bytes,
    media_type: str,
    *,
    max_side: int | None = None,
) -> tuple[bytes, str]:
    """
    Resize to max_side (default _MAX_DIMENSION) on the longest side and re-encode as JPEG.
    Returns (compressed_bytes, effective_media_type).

    Preserves aspect ratio. Skips resize if already small enough.
    """
    cap = _MAX_DIMENSION if max_side is None else max_side
    try:
        img: Image.Image = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) > cap:
            scale = cap / max(w, h)
            new_w = math.floor(w * scale)
            new_h = math.floor(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        if media_type == "image/png":
            img.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return buf.getvalue(), "image/jpeg"
        elif media_type == "image/webp":
            img.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return buf.getvalue(), "image/jpeg"
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.warning("compress_image_failed", error=str(exc))
        return image_bytes, media_type


def _bytes_to_jpeg_b64(image_bytes: bytes, *, quality: int = _JPEG_QUALITY) -> str:
    """Encode arbitrary image bytes as base64 JPEG (for preview_fast crops, no BG removal)."""
    img = Image.open(io.BytesIO(image_bytes))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _image_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:24]


# ── Multi-item deduplication ───────────────────────────────────────────────────


def _bbox_area(b: dict[str, float]) -> float:
    """Fractional area of a bbox dict with x_min/y_min/x_max/y_max keys."""
    w = max(0.0, b.get("x_max", 1.0) - b.get("x_min", 0.0))
    h = max(0.0, b.get("y_max", 1.0) - b.get("y_min", 0.0))
    return w * h


def _iou(a: dict[str, float], b: dict[str, float]) -> float:
    """Intersection-over-Union of two fractional bboxes."""
    ix1 = max(a.get("x_min", 0.0), b.get("x_min", 0.0))
    iy1 = max(a.get("y_min", 0.0), b.get("y_min", 0.0))
    ix2 = min(a.get("x_max", 1.0), b.get("x_max", 1.0))
    iy2 = min(a.get("y_max", 1.0), b.get("y_max", 1.0))
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0.0:
        return 0.0
    union = _bbox_area(a) + _bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def _filter_and_dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    1. Drop items below minimum bbox area or confidence threshold.
    2. Deduplicate: when two boxes overlap with IOU > threshold, keep the one
       with higher detection_confidence (or larger bbox if tied).
    Preserves original list order among survivors.
    """
    # Step 1 — filter low-quality / tiny detections
    filtered: list[dict[str, Any]] = []
    for item in items:
        bbox = item.get("bbox")
        if not isinstance(bbox, dict):
            bbox = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
        conf = float(item.get("detection_confidence") or item.get("confidence_score") or 0.0)
        area = _bbox_area(bbox)
        if area < _MIN_BBOX_AREA:
            logger.debug("item_dropped_too_small", item_id=item.get("item_id"), area=area)
            continue
        if conf < _MIN_CONFIDENCE:
            logger.debug("item_dropped_low_conf", item_id=item.get("item_id"), conf=conf)
            continue
        filtered.append(item)

    # Step 2 — NMS-style deduplication by IOU
    keep: list[dict[str, Any]] = []
    for candidate in filtered:
        bbox_c = candidate.get("bbox") or {}
        conf_c = float(candidate.get("detection_confidence") or 0.0)
        dominated = False
        for existing in keep:
            bbox_e = existing.get("bbox") or {}
            if _iou(bbox_c, bbox_e) > _IOU_DEDUP_THRESHOLD:
                conf_e = float(existing.get("detection_confidence") or 0.0)
                if conf_c <= conf_e:
                    dominated = True
                    break
                else:
                    keep.remove(existing)
                    break
        if not dominated:
            keep.append(candidate)

    if len(items) != len(keep):
        logger.info(
            "items_deduped",
            original=len(items),
            after_filter=len(filtered),
            kept=len(keep),
        )
    return keep


# ── Cache helpers ──────────────────────────────────────────────────────────────


async def _cache_get(key: str) -> dict[str, Any] | None:
    try:
        redis = await get_redis()
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _cache_set(key: str, data: dict[str, Any]) -> None:
    try:
        redis = await get_redis()
        await redis.set(key, json.dumps(data), ex=_CACHE_TTL)
    except Exception as exc:
        logger.debug("vision_cache_set_failed", error=str(exc))


# ── BG removal per item ────────────────────────────────────────────────────────


async def _remove_bg_timed(crop_bytes: bytes) -> tuple[bytes, str]:
    """
    Run BG removal with a per-item timeout.
    Returns (processed_bytes, status).
    """
    try:
        result = await asyncio.wait_for(
            remove_background_async(crop_bytes),
            timeout=_BG_TIMEOUT,
        )
        return result
    except TimeoutError:
        logger.warning("bg_removal_timeout")
        return crop_bytes, "failed"
    except Exception as exc:
        logger.warning("bg_removal_error", error=str(exc))
        return crop_bytes, "failed"


# ── Category normalisation ─────────────────────────────────────────────────────

_CAT_MAP: dict[str, str] = {
    "top": "tops",
    "tops": "tops",
    "bottom": "bottoms",
    "bottoms": "bottoms",
    "footwear": "shoes",
    "shoe": "shoes",
    "shoes": "shoes",
    "accessory": "accessories",
    "accessories": "accessories",
    "outerwear": "outerwear",
    "dress": "dresses",
    "dresses": "dresses",
    "other": "other",
}


def _norm_cat(raw: str | None) -> str:
    return _CAT_MAP.get(str(raw or "other").strip().lower(), "other")


def _bbox_to_normalized_model(raw: dict[str, Any]) -> NormalizedBoundingBox | None:
    xy = raw.get("bounding_box")
    if isinstance(xy, dict) and all(k in xy for k in ("x", "y", "width", "height")):
        try:
            return NormalizedBoundingBox(
                x=float(xy["x"]),
                y=float(xy["y"]),
                width=float(xy["width"]),
                height=float(xy["height"]),
            )
        except (TypeError, ValueError):
            pass
    b = raw.get("bbox")
    if isinstance(b, dict) and "x_min" in b:
        try:
            d = _bbox_to_xywh_dict(b)
            return NormalizedBoundingBox(**d)
        except (TypeError, ValueError):
            pass
    return None


# ── Main pipeline ──────────────────────────────────────────────────────────────


async def run_pipeline(
    image_bytes: bytes,
    media_type: str,
    scan_id: str,
    *,
    preview_fast: bool = False,
) -> VisionAnalyzeResponse:
    """
    Compress → cache → vision detection → per-item processing.

    ``preview_fast=True`` (closet analyze-preview): skips per-item BG removal and crop
    re-analysis (saves one OpenAI call per detected item + rembg time).
    """
    t0 = time.monotonic()

    fast_side = _MAX_DIMENSION_PREVIEW_FAST if preview_fast else None
    compressed, compressed_type = _compress_image(image_bytes, media_type, max_side=fast_side)
    logger.info(
        "vision_pipeline_start",
        scan_id=scan_id,
        original_kb=round(len(image_bytes) / 1024, 1),
        compressed_kb=round(len(compressed) / 1024, 1),
        preview_fast=preview_fast,
    )

    cache_key = _CACHE_KEY_PFX + ("fast:" if preview_fast else "") + _image_hash(compressed)
    cached_data = await _cache_get(cache_key)
    if cached_data:
        ms = round((time.monotonic() - t0) * 1000)
        logger.info("vision_pipeline_cache_hit", scan_id=scan_id, ms=ms, preview_fast=preview_fast)
        items = [VisionAnalysisItem(**i) for i in cached_data.get("items", [])]
        return VisionAnalyzeResponse(
            scan_id=scan_id,
            total_items_detected=len(items),
            items=items,
            processing_time_ms=ms,
            cached=True,
        )

    # 3. Vision AI — Gemini primary, OpenAI fallback
    try:
        raw_result = await _run_detection(compressed, compressed_type)
    except TimeoutError:
        ms = round((time.monotonic() - t0) * 1000)
        logger.error("vision_pipeline_timeout", scan_id=scan_id, ms=ms)
        return VisionAnalyzeResponse(
            scan_id=scan_id,
            total_items_detected=0,
            items=[],
            processing_time_ms=ms,
        )
    except Exception as exc:
        ms = round((time.monotonic() - t0) * 1000)
        logger.error("vision_pipeline_error", scan_id=scan_id, error=str(exc), ms=ms)
        return VisionAnalyzeResponse(
            scan_id=scan_id,
            total_items_detected=0,
            items=[],
            processing_time_ms=ms,
        )

    raw_items: list[dict[str, Any]] = _filter_and_dedup(raw_result.get("items") or [])
    if not raw_items:
        # Model may return valid boxes that all get dropped by area/confidence thresholds.
        # Keep a single best-effort detection (expand tiny boxes to full frame) so preview
        # still gets a crop instead of falling through to empty pipeline → confusing UX.
        orig = [x for x in (raw_result.get("items") or []) if isinstance(x, dict)]
        if orig:
            best = max(
                orig,
                key=lambda x: float(x.get("detection_confidence") or x.get("confidence_score") or 0.0),
            )
            relaxed = dict(best)
            bbox = relaxed.get("bbox")
            if not isinstance(bbox, dict):
                relaxed["bbox"] = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
            elif _bbox_area(cast(dict[str, float], bbox)) < _MIN_BBOX_AREA:
                relaxed["bbox"] = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}
            conf = float(relaxed.get("detection_confidence") or relaxed.get("confidence_score") or 0.0)
            if conf < _MIN_CONFIDENCE:
                relaxed["detection_confidence"] = _MIN_CONFIDENCE
            raw_items = [relaxed]
            logger.info(
                "vision_pipeline_recovered_after_filter_dropped_all",
                scan_id=scan_id,
            )
    if not raw_items:
        ms = round((time.monotonic() - t0) * 1000)
        return VisionAnalyzeResponse(
            scan_id=scan_id,
            total_items_detected=0,
            items=[],
            processing_time_ms=ms,
        )

    # Assign a stable detected_item_id to each raw item immediately after detection.
    # This UUID is the source of truth for image↔metadata correlation across the
    # entire pipeline: crop → BG removal → metadata enrichment → preview response → confirm.
    num_items = len(raw_items)
    for raw in raw_items:
        raw["detected_item_id"] = str(uuid4())

    # 4. Per item: full BG + OpenAI enrich, OR (preview_fast) JPEG crop only
    from app.api.v1.wardrobe.services.fashion_analysis_service import _crop_item

    async def _process_item(raw: dict[str, Any]) -> VisionAnalysisItem:
        detected_item_id: str = raw["detected_item_id"]
        bbox_raw = raw.get("bbox")
        has_valid_bbox = isinstance(bbox_raw, dict) and bool(bbox_raw)

        if not has_valid_bbox:
            if num_items > 1:
                # For multi-item detection, a missing bbox means we cannot reliably crop
                # this specific item — fall through to let caller collect as failed.
                logger.warning(
                    "item_missing_bbox_multi_item",
                    detected_item_id=detected_item_id,
                    category=raw.get("category"),
                )
                raise ValueError(
                    f"bbox missing for detected_item_id={detected_item_id} "
                    f"(category={raw.get('category')}) in multi-item detection. "
                    "Cannot crop without bbox."
                )
            # Single item — use full frame as bbox.
            bbox_raw = {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}

        bbox = cast(dict[str, float], bbox_raw)

        try:
            crop_bytes = _crop_item(image_bytes, bbox)
        except Exception as crop_exc:
            if num_items > 1:
                logger.warning(
                    "item_crop_failed_multi_item",
                    detected_item_id=detected_item_id,
                    error=str(crop_exc),
                )
                raise RuntimeError(f"crop failed for detected_item_id={detected_item_id}: {crop_exc}") from crop_exc
            logger.warning("item_crop_failed_single_item", detected_item_id=detected_item_id, error=str(crop_exc))
            crop_bytes = image_bytes

        if preview_fast:
            try:
                img_b64 = _bytes_to_jpeg_b64(crop_bytes, quality=_JPEG_QUALITY_FAST)
            except Exception as exc:
                logger.warning("preview_fast_jpeg_failed", detected_item_id=detected_item_id, error=str(exc))
                img_b64 = base64.b64encode(crop_bytes).decode("utf-8")
            merged = dict(raw)
            bg_status = "skipped_preview_fast"
            bg_removed = False
        else:
            final_bytes, bg_status = await _remove_bg_timed(crop_bytes)
            bg_removed = bg_status in ("success_rembg", "success_pil")
            img_b64 = base64.b64encode(final_bytes).decode("utf-8")

            merged = dict(raw)
            merged = await enrich_detection_with_crop_analysis(final_bytes, merged)

        bb_model = _bbox_to_normalized_model(raw)

        logger.debug(
            "item_pipeline_debug",
            detected_item_id=detected_item_id,
            category=_norm_cat(merged.get("category") or raw.get("category")),
            bbox=bbox,
            bg_status=bg_status,
            description=(str(merged.get("description") or raw.get("description") or ""))[:120],
        )

        return VisionAnalysisItem(
            detected_item_id=detected_item_id,
            item_id=str(raw.get("item_id") or detected_item_id),
            category=_norm_cat(merged.get("category") or raw.get("category")),
            subcategory=merged.get("subcategory") or raw.get("subcategory") or None,
            name=_build_name(merged),
            description=merged.get("description") or raw.get("description") or None,
            gender=str(merged.get("gender") or raw.get("gender") or "unisex"),
            fit=merged.get("fit") or raw.get("fit") or None,
            sleeve_type=merged.get("sleeve_type") or raw.get("sleeve_type") or None,
            primary_color=merged.get("primary_color") or raw.get("primary_color") or None,
            secondary_color=merged.get("secondary_color") or raw.get("secondary_color") or None,
            pattern=merged.get("pattern") or raw.get("pattern") or None,
            material=merged.get("material") or raw.get("material") or None,
            brand=merged.get("brand") or raw.get("brand") or None,
            occasions=list(merged.get("occasions") or raw.get("occasions") or []),
            season=list(merged.get("season") or raw.get("season") or []),
            style_tags=list(merged.get("style_tags") or raw.get("style_tags") or []),
            bounding_box=bb_model,
            image_base64=img_b64,
            processed_image=img_b64,
            confidence_score=float(merged.get("detection_confidence") or raw.get("detection_confidence") or 0.0),
            background_removed=bg_removed,
            background_removal_status=bg_status,
            segmentation_quality=str(merged.get("segmentation_quality") or raw.get("segmentation_quality") or "medium"),
        )

    # Run all items in parallel; collect failures per-item so one bad crop doesn't abort all.
    gather_results: list[VisionAnalysisItem | BaseException] = await asyncio.gather(
        *[_process_item(raw) for raw in raw_items],
        return_exceptions=True,
    )

    processed_items: list[VisionAnalysisItem] = []
    failed_items: list[dict[str, Any]] = []
    for i, result in enumerate(gather_results):
        raw = raw_items[i]
        if isinstance(result, BaseException):
            failed_items.append(
                {
                    "detected_item_id": raw.get("detected_item_id", "unknown"),
                    "category": raw.get("category"),
                    "error": str(result),
                }
            )
            logger.warning(
                "item_processing_failed",
                detected_item_id=raw.get("detected_item_id"),
                error=str(result),
            )
        else:
            processed_items.append(result)

    ms = round((time.monotonic() - t0) * 1000)
    from app.core.metrics import record_vision_stage

    record_vision_stage("total", (time.monotonic() - t0))
    logger.info(
        "vision_pipeline_complete",
        scan_id=scan_id,
        items=len(processed_items),
        failed=len(failed_items),
        ms=ms,
        preview_fast=preview_fast,
    )

    # 5. Cache the result (strip image bytes — they are per-request and must be re-cropped on hit)
    cacheable = {
        "items": [
            {k: v for k, v in item.model_dump().items() if k not in ("image_base64", "processed_image")}
            for item in processed_items
        ]
    }
    await _cache_set(cache_key, cacheable)

    return VisionAnalyzeResponse(
        scan_id=scan_id,
        total_items_detected=len(processed_items),
        items=processed_items,
        processing_time_ms=ms,
        cached=False,
        failed_items=failed_items,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_name(raw: dict[str, Any]) -> str:
    """Build a human-friendly item name from vision metadata."""
    # Prefer the AI-generated name if present and meaningful
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


# ── Detection router (Gemini → OpenAI fallback) ───────────────────────────────


async def _run_detection(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    """
    Choose Gemini 1.5 Flash (fast) when configured, fall back to GPT-4o.
    Returns the standard detection dict shape.
    """
    from app.api.v1.intelligence.services import gemini_service  # lazy import to avoid circular deps

    if gemini_service.is_available():
        try:
            return await asyncio.wait_for(
                gemini_service.detect_and_classify(image_bytes, media_type),
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("gemini_detection_failed", error=str(exc), fallback="openai")

    # OpenAI fallback
    return await asyncio.wait_for(
        fashion_analysis_service.detect_fashion_items(image_bytes, media_type),
        timeout=_VISION_TIMEOUT,
    )


# ── Streaming pipeline ────────────────────────────────────────────────────────


async def run_pipeline_streaming(
    image_bytes: bytes,
    media_type: str,
    scan_id: str,
):
    """
    Async generator that yields SSE-formatted strings.

    Event types emitted:
      {"type":"stage",          "stage": str, "message": str}
      {"type":"items_detected", "count": int, "cached": bool, "items": [...metadata...]}
      {"type":"item_ready",     "item_id": str, "image_base64": str,
                                "background_removed": bool, "background_removal_status": str}
      {"type":"complete",       "scan_id": str, "total_items": int, "processing_time_ms": int}
      {"type":"error",          "message": str}

    Yields strings already formatted as SSE lines (``data: {...}\\n\\n``).
    """
    import uuid as _uuid

    def _sse(data: dict[str, Any]) -> str:
        return f"data: {json.dumps(data)}\n\n"

    t0 = time.monotonic()

    # ── Stage 1: Compress ────────────────────────────────────────────────────
    compressed, compressed_type = _compress_image(image_bytes, media_type)
    logger.info(
        "stream_pipeline_start",
        scan_id=scan_id,
        orig_kb=round(len(image_bytes) / 1024, 1),
        comp_kb=round(len(compressed) / 1024, 1),
    )

    # ── Stage 2: Cache check ─────────────────────────────────────────────────
    cache_key = _CACHE_KEY_PFX + _image_hash(compressed)
    cached_data = await _cache_get(cache_key)

    if cached_data:
        raw_items: list[dict[str, Any]] = cached_data.get("items", [])
        yield _sse(
            {
                "type": "items_detected",
                "count": len(raw_items),
                "cached": True,
                "items": raw_items,
            }
        )
    else:
        # ── Stage 3: Detection ───────────────────────────────────────────────
        yield _sse({"type": "stage", "stage": "detecting", "message": "Detecting clothing items with AI..."})

        try:
            raw_result = await _run_detection(compressed, compressed_type)
        except TimeoutError:
            yield _sse({"type": "error", "message": "Detection timed out. Please try again."})
            return
        except Exception as exc:
            logger.error("stream_detection_error", scan_id=scan_id, error=str(exc))
            yield _sse({"type": "error", "message": f"Detection failed: {exc}"})
            return

        raw_items = _filter_and_dedup(raw_result.get("items") or [])

        # Assign stable detected_item_id to each raw item immediately after detection.
        for raw in raw_items:
            raw["detected_item_id"] = str(_uuid.uuid4())

        # Stream metadata immediately — frontend renders cards before images arrive.
        # Include detected_item_id so frontend can correlate item_ready events by id,
        # not by arrival order (which is non-deterministic for parallel BG tasks).
        items_meta = [{k: v for k, v in item.items() if k not in ("image_base64",)} for item in raw_items]
        yield _sse(
            {
                "type": "items_detected",
                "count": len(raw_items),
                "cached": False,
                "items": items_meta,
            }
        )

        if not raw_items:
            ms = round((time.monotonic() - t0) * 1000)
            yield _sse({"type": "complete", "scan_id": scan_id, "total_items": 0, "processing_time_ms": ms})
            return

    # ── Stage 4: Parallel BG removal — stream items as each finishes ─────────
    yield _sse(
        {"type": "stage", "stage": "backgrounds", "message": f"Removing backgrounds from {len(raw_items)} item(s)..."}
    )

    from app.api.v1.wardrobe.services.fashion_analysis_service import _crop_item

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _process_and_queue(raw: dict[str, Any]) -> None:
        # Use the stable detected_item_id assigned right after detection.
        detected_item_id: str = raw["detected_item_id"]
        item_id = raw.get("item_id") or detected_item_id
        bbox = raw.get("bbox") or {}
        try:
            crop = _crop_item(image_bytes, bbox)
        except Exception as exc:
            logger.warning("stream_crop_failed", detected_item_id=detected_item_id, error=str(exc))
            crop = image_bytes

        bg_bytes, bg_status = await _remove_bg_timed(crop)
        bg_removed = bg_status in ("success_rembg", "success_pil")
        img_b64 = base64.b64encode(bg_bytes).decode("utf-8")

        # Normalise bounding_box to {x, y, width, height} as per output spec
        bounding_box: dict[str, float] | None = None
        if isinstance(bbox, dict) and "x_min" in bbox:
            bounding_box = {
                "x": float(bbox.get("x_min", 0.0)),
                "y": float(bbox.get("y_min", 0.0)),
                "width": max(0.0, float(bbox.get("x_max", 1.0)) - float(bbox.get("x_min", 0.0))),
                "height": max(0.0, float(bbox.get("y_max", 1.0)) - float(bbox.get("y_min", 0.0))),
            }

        conf = float(raw.get("detection_confidence") or raw.get("confidence_score") or 0.0)

        logger.debug(
            "stream_item_ready",
            detected_item_id=detected_item_id,
            category=_norm_cat(raw.get("category")),
            bg_status=bg_status,
            description=(str(raw.get("description") or ""))[:120],
        )

        await queue.put(
            {
                "type": "item_ready",
                # detected_item_id is the stable key — frontend must use this, not array index.
                "detected_item_id": detected_item_id,
                "item_id": item_id,
                # ── image ─────────────────────────────────────────────────────────
                "image_base64": img_b64,
                "background_removed": bg_removed,
                "background_removal_status": bg_status,
                # ── spatial ───────────────────────────────────────────────────────
                "bounding_box": bounding_box,
                # ── classification ────────────────────────────────────────────────
                "category": _norm_cat(raw.get("category")),
                "subcategory": raw.get("subcategory") or None,
                "name": _build_name(raw),
                "description": raw.get("description") or None,
                "gender": str(raw.get("gender") or "unisex"),
                "fit": raw.get("fit") or None,
                "sleeve_type": raw.get("sleeve_type") or None,
                # ── attributes ────────────────────────────────────────────────────
                "primary_color": raw.get("primary_color") or None,
                "secondary_color": raw.get("secondary_color") or None,
                "pattern": raw.get("pattern") or None,
                "material": raw.get("material") or None,
                "brand": raw.get("brand") or None,
                # ── taxonomy ──────────────────────────────────────────────────────
                "occasions": list(raw.get("occasions") or []),
                "season": list(raw.get("season") or []),
                "style_tags": list(raw.get("style_tags") or []),
                # ── quality ───────────────────────────────────────────────────────
                "confidence_score": conf,
                "segmentation_quality": str(raw.get("segmentation_quality") or "medium"),
            }
        )

    # Kick off all BG tasks concurrently
    tasks = [asyncio.create_task(_process_and_queue(raw)) for raw in raw_items]
    total = len(tasks)
    completed = 0

    try:
        while completed < total:
            event = await asyncio.wait_for(queue.get(), timeout=60.0)
            yield _sse(event)
            completed += 1
    except TimeoutError:
        for t in tasks:
            t.cancel()
        yield _sse({"type": "error", "message": "Background removal timed out."})
        return
    except Exception as exc:
        for t in tasks:
            t.cancel()
        yield _sse({"type": "error", "message": f"Processing error: {exc}"})
        return

    # ── Stage 5: Cache metadata + emit complete ───────────────────────────────
    if not cached_data:
        cacheable = {"items": [{k: v for k, v in i.items() if k != "image_base64"} for i in raw_items]}
        await _cache_set(cache_key, cacheable)

    ms = round((time.monotonic() - t0) * 1000)
    logger.info("stream_pipeline_complete", scan_id=scan_id, items=total, ms=ms)
    yield _sse({"type": "complete", "scan_id": scan_id, "total_items": total, "processing_time_ms": ms})
