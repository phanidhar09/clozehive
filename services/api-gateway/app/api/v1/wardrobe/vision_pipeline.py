"""
Vision Pipeline endpoints — /api/v1/closet/

POST  /analyze-vision/stream       ★ STREAMING — SSE real-time detection + BG removal.
POST  /analyze-vision              Batch (waits for all items; legacy / non-JS clients).
POST  /save-analyzed-items         Save reviewed items to the closet database.
POST  /{item_id}/remove-background Retry background removal for a saved item.

Streaming design
----------------
POST /analyze-vision/stream returns text/event-stream via StreamingResponse.
The frontend uses fetch() + ReadableStream (not EventSource — POST body needed).

SSE event sequence:
  {"type":"stage",          "stage":"detecting",  "message":"..."}
  {"type":"items_detected", "count":N, "cached":bool, "items":[...metadata...]}
  {"type":"stage",          "stage":"backgrounds","message":"..."}
  {"type":"item_ready",     "item_id":"...", "image_base64":"...",
                             "background_removed":bool, "background_removal_status":"..."}
  …one item_ready per item, in completion order (fastest BG first)…
  {"type":"complete",       "scan_id":"...", "total_items":N, "processing_time_ms":M}

The X-Accel-Buffering: no header disables nginx proxy buffering so events
reach the browser without delay.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.wardrobe.repositories.closet_repo import ClosetRepository
from app.api.v1.wardrobe.schemas.closet import (
    ClosetItemResponse,
    SaveAnalyzedItemsRequest,
    SaveAnalyzedItemsResponse,
    VisionAnalyzeResponse,
)
from app.api.v1.wardrobe.services import similarity_service, vision_pipeline_service
from app.api.v1.wardrobe.services.background_removal_service import remove_background_async
from app.core import cache_service
from app.core.deps import CurrentUser
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.upload_service import persist_upload, read_upload_bytes, read_validated_image
from app.db.session import get_session
from app.models.closet import ClosetItem

router = APIRouter(tags=["Vision Pipeline"])
logger = get_logger("vision_pipeline_api")

# ── Category normalisation (matches DB Literal constraint) ────────────────────

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

_VALID_CATEGORIES = frozenset(_CAT_MAP.values())


def _norm_cat(raw: str | None) -> str:
    cat = str(raw or "other").strip().lower()
    return _CAT_MAP.get(cat, "other")


def _pick_season(season_list: list[str] | None) -> list[str]:
    """Return a deduplicated list of valid season values from the AI response."""
    valid = {"spring", "summer", "fall", "winter"}
    result: list[str] = []
    seen: set[str] = set()
    for s in season_list or []:
        mapped = "fall" if s.strip().lower() == "autumn" else s.strip().lower()
        if mapped in valid and mapped not in seen:
            result.append(mapped)
            seen.add(mapped)
    return result


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ── POST /analyze-vision/stream ──────────────────────────────────────────────


@router.post(
    "/analyze-vision/stream",
    summary="Streaming: detect clothing items + BG removal with real-time SSE events",
    response_class=StreamingResponse,
)
async def analyze_vision_stream(
    user_id: CurrentUser,
    file: UploadFile = File(..., description="Single outfit/clothing image (JPEG/PNG/WebP, ≤10 MB)"),
) -> StreamingResponse:
    """
    Upload one photo and receive Server-Sent Events as processing progresses.

    The frontend connects via ``fetch()`` + ``ReadableStream``:
    ``POST /analyze-vision/stream`` with the image as multipart/form-data.

    Events are delivered immediately:
    - ``items_detected``: all item metadata (category, colors, etc.) — arrives after ~1–3 s
    - ``item_ready``: transparent PNG image per item — arrives progressively as BG is removed
    - ``complete``: final timing summary

    Perceived performance: first item appears in ~2–5 s regardless of total count.
    """
    image_bytes, content_type = await read_validated_image(file)
    scan_id = str(uuid.uuid4())

    logger.info(
        "analyze_vision_stream_request",
        user_id=user_id,
        filename=file.filename,
        size_kb=round(len(image_bytes) / 1024, 1),
        scan_id=scan_id,
    )

    return StreamingResponse(
        vision_pipeline_service.run_pipeline_streaming(image_bytes, content_type, scan_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )


# ── POST /analyze-vision ───────────────────────────────────────────────────────


@router.post(
    "/analyze-vision",
    response_model=VisionAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze a single image — detect ALL clothing items with BG removal",
)
async def analyze_vision(
    user_id: CurrentUser,
    file: UploadFile = File(..., description="Single clothing/outfit image (JPEG/PNG/WebP, ≤10 MB)"),
) -> VisionAnalyzeResponse:
    """
    Upload one photo containing any number of clothing items.

    The pipeline:
    1. Compresses the image (saves AI tokens → faster analysis).
    2. Checks a Redis cache keyed on the image hash (repeat submissions are free).
    3. Sends to OpenAI Vision to detect every item with bounding boxes + metadata.
    4. Runs background removal concurrently on each item crop.
    5. Returns structured JSON with base64 transparent-PNG previews.

    Typical latency: **6–15 s** for a 3-item photo (≤ 45 s timeout).
    Cache hits return in **< 100 ms**.
    """
    image_bytes, content_type = await read_validated_image(file)
    scan_id = str(uuid.uuid4())

    logger.info(
        "analyze_vision_request",
        user_id=user_id,
        filename=file.filename,
        size_kb=round(len(image_bytes) / 1024, 1),
        scan_id=scan_id,
    )

    result = await vision_pipeline_service.run_pipeline(image_bytes, content_type, scan_id)

    logger.info(
        "analyze_vision_complete",
        user_id=user_id,
        scan_id=scan_id,
        items=result.total_items_detected,
        ms=result.processing_time_ms,
        cached=result.cached,
    )
    return result


# ── POST /save-analyzed-items ─────────────────────────────────────────────────


@router.post(
    "/save-analyzed-items",
    response_model=SaveAnalyzedItemsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save AI-analyzed items to the closet database",
)
async def save_analyzed_items(
    body: SaveAnalyzedItemsRequest,
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> SaveAnalyzedItemsResponse:
    """
    Persist reviewed items from the Vision AI scan into the closet.

    For each item:
    - If ``image_base64`` is provided, decodes the BG-removed PNG and saves it
      to disk as the *processed* image (used in closet thumbnails).
    - ``image_url`` (the main closet-grid URL) is set to ``processed_image_url``
      when background removal succeeded, otherwise to ``original_image_url``.
    - All fashion metadata is stored verbatim from the analysis.
    - ``scan_batch_id`` groups items from the same scan for dedup / history.
    """
    if not body.save_permission:
        raise BadRequestError(
            "save_permission must be true. The user must explicitly confirm before items are saved to the closet."
        )
    if not body.items:
        raise BadRequestError("No items provided to save.")
    if len(body.items) > 30:
        raise BadRequestError("Maximum 30 items per save request.")

    user_uuid = UUID(user_id)
    batch_id = body.scan_batch_id or str(uuid.uuid4())

    saved: list[ClosetItemResponse] = []
    failed: list[dict[str, Any]] = []

    for req in body.items:
        try:
            # Decode and persist the BG-removed image if provided
            processed_url: str | None = None
            if req.image_base64:
                try:
                    img_bytes = base64.b64decode(req.image_base64)
                    processed_url = await persist_upload(img_bytes, "image/png", f"{req.item_id}_processed.png")
                except Exception as exc:
                    logger.warning("save_image_decode_failed", item_id=req.item_id, error=str(exc))

            # Primary image: processed (BG removed) > original
            primary_url = processed_url or req.original_image_url

            # Category → DB canonical form
            db_category = _norm_cat(req.category)

            # Build tag list from style_tags + subcategory
            tags: list[str] = []
            if req.subcategory:
                tags.append(req.subcategory)
            tags.extend(req.style_tags or [])
            seen: set[str] = set()
            deduped_tags = [t for t in tags if not (t.lower() in seen or seen.add(t.lower()))][:20]  # type: ignore[func-returns-value]

            new_item = ClosetItem(
                user_id=user_uuid,
                name=req.name or "Clothing Item",
                category=db_category,
                color=req.primary_color or None,
                fabric=req.material or None,
                pattern=req.pattern or None,
                season=_pick_season(req.season),
                occasion=req.occasions or [],
                tags=deduped_tags,
                image_url=primary_url,
                notes=req.description or None,
                brand=req.brand or None,
                # Vision pipeline fields
                original_image_url=req.original_image_url or None,
                processed_image_url=processed_url,
                background_removed=req.background_removed,
                background_removal_status=req.background_removal_status,
                analysis_source="vision_ai",
                confidence_score=_safe_float(req.confidence_score),
                scan_batch_id=batch_id,
            )
            session.add(new_item)
            await session.flush()

            saved_response = ClosetItemResponse.model_validate(new_item)
            saved.append(saved_response)

        except Exception as exc:
            logger.error("save_analyzed_item_failed", item_id=req.item_id, error=str(exc))
            failed.append({"item_id": req.item_id, "name": req.name, "error": str(exc)})

    if saved:
        redis = await get_redis()
        await cache_service.invalidate_user_ai_cache(redis, user_id)
        # Commit before scheduling the embedding refresh (durable ARQ job when
        # HEAVY_WORK_ASYNC is on, else in-process BackgroundTask): the job opens
        # its own session and cannot see this request's uncommitted rows.
        await session.commit()
        for saved_item in saved:
            await similarity_service.schedule_embedding_update(background_tasks, str(saved_item.id))

    logger.info(
        "save_analyzed_items_complete",
        user_id=user_id,
        saved=len(saved),
        failed=len(failed),
        batch_id=batch_id,
    )

    return SaveAnalyzedItemsResponse(
        saved=saved,
        failed=failed,
        total_saved=len(saved),
        total_failed=len(failed),
    )


# ── POST /{item_id}/remove-background ─────────────────────────────────────────


@router.post(
    "/{item_id}/remove-background",
    response_model=ClosetItemResponse,
    summary="Retry background removal for a saved closet item",
)
async def retry_remove_background(
    item_id: UUID,
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ClosetItemResponse:
    """
    Re-run background removal on the item's original image.

    - Reads ``original_image_url`` (or ``image_url`` as fallback).
    - Runs the improved BG removal (rembg if available, PIL otherwise).
    - Updates ``processed_image_url``, ``background_removed``, and
      ``background_removal_status`` in the database.
    - Sets ``image_url`` to the new processed image so the closet grid updates.

    Returns the updated ClosetItemResponse.
    """
    repo = ClosetRepository(session)
    item = await repo.get_owned(item_id, UUID(user_id))
    if not item:
        raise NotFoundError(f"Item {item_id} not found.")

    source_url = item.original_image_url or item.image_url
    if not source_url:
        raise BadRequestError("No source image available for background removal.")

    # Load image bytes from GCS or local disk depending on where the URL points
    try:
        img_bytes = await asyncio.to_thread(read_upload_bytes, source_url)
    except BadRequestError:
        raise
    except Exception as exc:
        raise BadRequestError(f"Could not read source image: {exc}") from exc

    # Run BG removal
    try:
        processed_bytes, bg_status = await asyncio.wait_for(
            remove_background_async(img_bytes),
            timeout=30.0,
        )
    except TimeoutError:
        raise BadRequestError("Background removal timed out. Please try again.")

    bg_removed = bg_status in ("success_rembg", "success_pil")

    # Persist the new processed image
    new_processed_url = await persist_upload(processed_bytes, "image/png", f"retry_{item_id}.png")

    # Update item in DB
    updated = await repo.update(
        item,
        processed_image_url=new_processed_url,
        background_removed=bg_removed,
        background_removal_status=bg_status,
        image_url=new_processed_url if bg_removed else (item.original_image_url or item.image_url),
    )

    redis = await get_redis()
    await cache_service.invalidate_user_ai_cache(redis, user_id)

    logger.info(
        "bg_retry_complete",
        user_id=user_id,
        item_id=str(item_id),
        status=bg_status,
    )
    return ClosetItemResponse.model_validate(updated)
