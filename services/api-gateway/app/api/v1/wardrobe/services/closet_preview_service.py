"""Stage closet image analysis in Redis; DB rows are created only on confirm."""

from __future__ import annotations

import base64
from typing import Any
from uuid import UUID, uuid4

from app.api.v1.wardrobe.schemas.closet import (
    ClosetAnalyzePreviewResponse,
    ClosetConfirmItemPayload,
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetPreviewItem,
)
from app.api.v1.wardrobe.schemas.vision_canonical import (
    NormalizedVisionAIOutput,
    parse_vision_ai_payload,
    vision_analysis_item_to_normalized,
)
from app.api.v1.wardrobe.services import vision_service
from app.api.v1.wardrobe.services.background_removal_service import remove_background_async
from app.api.v1.wardrobe.services.vision_pipeline_service import run_pipeline
from app.core import cache_service
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.upload_service import persist_upload, signed_url_for_stored

logger = get_logger("closet_preview")
settings = get_settings()


def _sign_preview_items(items: list[ClosetPreviewItem]) -> list[ClosetPreviewItem]:
    """Swap stored GCS URLs for short-lived signed URLs on the outgoing response.

    Applied AFTER the preview session is cached, and only mutates the response
    objects — the cached ``slots`` keep their raw URLs, so ``confirm_preview``
    (which reads URLs from the server-side slot) is unaffected. No-op unless
    GCS_SIGNED_URLS is enabled.
    """
    if not settings.gcs_signed_urls:
        return items
    for it in items:
        it.original_image_url = signed_url_for_stored(it.original_image_url) or it.original_image_url
        it.preview_image_url = signed_url_for_stored(it.preview_image_url) or it.preview_image_url
        it.processed_image_url = signed_url_for_stored(it.processed_image_url)
    return items


def preview_session_key(session_id: str) -> str:
    return cache_service.namespaced_key("closet_preview", session_id)


def _preview_from_normalized(
    slot_index: int,
    temp_id: str,
    n: NormalizedVisionAIOutput,
    *,
    original_image_url: str,
    preview_image_url: str,
    processed_image_url: str | None,
    background_removed: bool,
    background_removal_status: str | None,
    detected_item_id: str | None = None,
) -> ClosetPreviewItem:
    return ClosetPreviewItem(
        slot_index=slot_index,
        temp_id=temp_id,
        detected_item_id=detected_item_id,
        name=n.name,
        category=n.category,
        subcategory=n.subcategory,
        color=n.color,
        brand=n.brand,
        material=n.material,
        pattern=n.pattern,
        fit=n.fit,
        season=list(n.season),
        occasions=list(n.occasions),
        description=n.description,
        confidence=n.confidence,
        original_image_url=original_image_url,
        preview_image_url=preview_image_url,
        processed_image_url=processed_image_url,
        background_removed=background_removed,
        background_removal_status=background_removal_status,
        style_tags=list(n.style_tags),
    )


async def _append_bulk_fallback_preview(
    *,
    image_bytes: bytes,
    content_type: str,
    original_url: str,
    slots: list[dict[str, Any]],
    preview_items: list[ClosetPreviewItem],
    slot_index: int,
    temp_id: str,
) -> None:
    """Single-image holistic analysis + optional full-image BG removal (preview_confirm path)."""
    try:
        bulk = await vision_service.analyze_for_bulk(image_bytes, content_type)
    except Exception as exc:
        logger.error("analyze_for_bulk_failed", error=str(exc))
        bulk = {}
    n = parse_vision_ai_payload(bulk if isinstance(bulk, dict) else {}, source="bulk")
    proc_url = original_url
    bg_removed = False
    bg_status: str | None = "not_attempted"
    if not settings.vision_preview_fast:
        try:
            png, bg_status = await remove_background_async(image_bytes)
            if bg_status in ("success_rembg", "success_pil"):
                proc_url = await persist_upload(png, "image/png", None)
                bg_removed = True
        except Exception as exc:
            logger.warning("preview_full_bg_failed", error=str(exc))
    else:
        bg_status = "skipped_preview_fast"

    prev_url = proc_url
    slots.append(
        {
            "slot_index": slot_index,
            "temp_id": temp_id,
            "detected_item_id": temp_id,
            "original_image_url": original_url,
            "crop_image_url": prev_url,
            "processed_image_url": proc_url,
            "background_removed": bg_removed,
            "background_removal_status": bg_status,
            "confidence_score": float(n.confidence),
        }
    )
    preview_items.append(
        _preview_from_normalized(
            slot_index,
            temp_id,
            n,
            original_image_url=original_url,
            preview_image_url=prev_url,
            processed_image_url=proc_url,
            background_removed=bg_removed,
            background_removal_status=bg_status,
            detected_item_id=temp_id,
        )
    )


def _append_minimal_placeholder_preview(
    *,
    original_url: str,
    slots: list[dict[str, Any]],
    preview_items: list[ClosetPreviewItem],
    slot_index: int,
    temp_id: str,
    message: str,
) -> None:
    """Last-resort row so the client always gets an editable preview (no external calls)."""
    n = parse_vision_ai_payload(
        {
            "name": "Clothing Item",
            "category": "other",
            "description": message,
            "confidence_score": 0.0,
        },
        source="fallback",
    )
    slots.append(
        {
            "slot_index": slot_index,
            "temp_id": temp_id,
            "detected_item_id": temp_id,
            "original_image_url": original_url,
            "crop_image_url": original_url,
            "processed_image_url": original_url,
            "background_removed": False,
            "background_removal_status": "not_attempted",
            "confidence_score": float(n.confidence),
        }
    )
    preview_items.append(
        _preview_from_normalized(
            slot_index,
            temp_id,
            n,
            original_image_url=original_url,
            preview_image_url=original_url,
            processed_image_url=original_url,
            background_removed=False,
            background_removal_status="not_attempted",
            detected_item_id=temp_id,
        )
    )


async def _recrop_from_source(
    image_bytes: bytes,
    vitem: Any,
    detected_item_id: str,
    original_url: str,
) -> tuple[str, bool]:
    """
    Re-crop a detected item from source bytes using its bounding_box.

    Used when image_base64 is absent (cache hit) — returns (proc_url, success).
    Falls back to original_url if bounding_box is missing or crop fails.
    """
    from app.api.v1.wardrobe.services.fashion_analysis_service import _crop_item

    bb = getattr(vitem, "bounding_box", None)
    if bb is None:
        logger.warning(
            "recrop_skipped_no_bbox",
            detected_item_id=detected_item_id,
            fallback="original_url",
        )
        return original_url, False

    bbox_dict = {
        "x_min": float(bb.x),
        "y_min": float(bb.y),
        "x_max": float(bb.x + bb.width),
        "y_max": float(bb.y + bb.height),
    }
    try:
        crop = _crop_item(image_bytes, bbox_dict)
        url = await persist_upload(crop, "image/png", f"{detected_item_id}_crop.png")
        logger.info("recropped_from_source_on_cache_hit", detected_item_id=detected_item_id)
        return url, True
    except Exception as exc:
        logger.warning(
            "recrop_failed_using_original",
            detected_item_id=detected_item_id,
            error=str(exc),
        )
        return original_url, False


async def analyze_preview(
    user_id: UUID,
    *,
    image_bytes: bytes,
    content_type: str,
    filename: str | None,
) -> ClosetAnalyzePreviewResponse:
    original_url = await persist_upload(image_bytes, content_type, filename)
    scan_id = str(uuid4())
    pipeline = await run_pipeline(
        image_bytes,
        content_type,
        scan_id,
        preview_fast=settings.vision_preview_fast,
    )

    preview_session_id = uuid4()
    slots: list[dict[str, Any]] = []
    preview_items: list[ClosetPreviewItem] = []

    if pipeline.items:
        for idx, vitem in enumerate(pipeline.items):
            # Use the stable detected_item_id generated at detection time; fall back to item_id.
            detected_item_id: str = getattr(vitem, "detected_item_id", None) or vitem.item_id

            n = vision_analysis_item_to_normalized(vitem)
            bg_removed = bool(vitem.background_removed)
            bg_status = vitem.background_removal_status or "not_attempted"
            raw_b64 = vitem.image_base64 or vitem.processed_image

            if raw_b64:
                # Fresh pipeline run — image_base64 holds the per-item crop/BG-removed bytes.
                try:
                    png = base64.b64decode(raw_b64)
                    proc_url = await persist_upload(png, "image/png", f"{detected_item_id}.png")
                    logger.debug(
                        "closet_preview_item_persisted",
                        detected_item_id=detected_item_id,
                        slot_index=idx,
                        category=n.category,
                        description=(n.description or "")[:100],
                        proc_url=proc_url,
                        bg_status=bg_status,
                    )
                except Exception as exc:
                    logger.warning(
                        "preview_persist_crop_failed",
                        detected_item_id=detected_item_id,
                        error=str(exc),
                    )
                    proc_url = original_url
                    bg_removed = False
                    bg_status = "failed"
            else:
                # Cache hit: image_base64 is intentionally absent in cached payload.
                # Re-crop from source bytes using the stored bounding_box so every
                # item still gets its own image rather than the full original.
                proc_url, _recrop_ok = await _recrop_from_source(image_bytes, vitem, detected_item_id, original_url)
                if not _recrop_ok:
                    bg_removed = False
                    bg_status = "cache_hit_no_bbox"
                else:
                    bg_status = "cache_hit_recropped"
                logger.debug(
                    "closet_preview_item_cache_hit",
                    detected_item_id=detected_item_id,
                    slot_index=idx,
                    category=n.category,
                    proc_url=proc_url,
                    bg_status=bg_status,
                )

            prev_url = proc_url or original_url
            slots.append(
                {
                    "slot_index": idx,
                    "temp_id": vitem.item_id,
                    "detected_item_id": detected_item_id,
                    "original_image_url": original_url,
                    "crop_image_url": prev_url,
                    "processed_image_url": proc_url,
                    "background_removed": bg_removed,
                    "background_removal_status": bg_status,
                    "confidence_score": float(n.confidence),
                }
            )

            preview_items.append(
                _preview_from_normalized(
                    idx,
                    vitem.item_id,
                    n,
                    original_image_url=original_url,
                    preview_image_url=prev_url,
                    processed_image_url=proc_url,
                    background_removed=bg_removed,
                    background_removal_status=bg_status,
                    detected_item_id=detected_item_id,
                )
            )
    else:
        await _append_bulk_fallback_preview(
            image_bytes=image_bytes,
            content_type=content_type,
            original_url=original_url,
            slots=slots,
            preview_items=preview_items,
            slot_index=0,
            temp_id="fallback-0",
        )

    if not preview_items:
        next_idx = max((int(s["slot_index"]) for s in slots), default=-1) + 1
        logger.warning("closet_preview_forcing_bulk_fallback", scan_id=scan_id, slot_index=next_idx)
        await _append_bulk_fallback_preview(
            image_bytes=image_bytes,
            content_type=content_type,
            original_url=original_url,
            slots=slots,
            preview_items=preview_items,
            slot_index=next_idx,
            temp_id=f"fallback-{uuid4().hex[:10]}",
        )

    if not preview_items:
        next_idx = max((int(s["slot_index"]) for s in slots), default=-1) + 1
        logger.error(
            "closet_preview_minimal_placeholder_after_failed_vision",
            scan_id=scan_id,
            slot_index=next_idx,
        )
        _append_minimal_placeholder_preview(
            original_url=original_url,
            slots=slots,
            preview_items=preview_items,
            slot_index=next_idx,
            temp_id=f"minimal-{uuid4().hex[:10]}",
            message=(
                "Vision preview produced no rows (check OPENAI_API_KEY / gateway logs). Edit details below, then save."
            ),
        )

    session_payload: dict[str, Any] = {
        "user_id": str(user_id),
        "scan_id": scan_id,
        "slots": slots,
    }
    key = preview_session_key(str(preview_session_id))
    ok = await cache_service.set(key, session_payload, settings.closet_preview_ttl_seconds)
    if not ok:
        raise ServiceUnavailableError(
            "Could not stage upload preview.",
            detail="Redis is required for the preview session. Check REDIS_URL and try again.",
        )

    logger.info(
        "closet_preview_complete",
        scan_id=scan_id,
        item_count=len(preview_items),
        pipeline_items=len(pipeline.items or []),
    )
    return ClosetAnalyzePreviewResponse(
        preview_session_id=preview_session_id,
        items=_sign_preview_items(preview_items),
        scan_id=scan_id,
        pipeline_cached=pipeline.cached,
    )


async def confirm_preview(
    user_id: UUID,
    *,
    preview_session_id: UUID,
    items: list[ClosetConfirmItemPayload],
    create_item,
) -> list[ClosetItemResponse]:
    """
    Persist selected preview slots as closet items.

    Image URLs come exclusively from the server-side slot (keyed by slot_index).
    Metadata comes from the client payload. This guarantees image ↔ metadata
    stay locked to the same detected_item_id established at detection time.

    ``create_item`` must be ``ClosetService.create_item(user_id, ClosetItemCreate) -> ClosetItemResponse``.
    """
    key = preview_session_key(str(preview_session_id))
    session = await cache_service.get(key)
    if not session:
        raise NotFoundError("Preview session expired or not found. Run analyze again.")

    if str(session.get("user_id")) != str(user_id):
        raise BadRequestError("Invalid preview session.")

    slots: list[dict[str, Any]] = session.get("slots") or []
    # Primary lookup by slot_index; secondary index by detected_item_id for validation.
    by_index = {int(s["slot_index"]): s for s in slots}
    by_detected_id = {str(s.get("detected_item_id", "")): s for s in slots if s.get("detected_item_id")}

    saved: list[ClosetItemResponse] = []
    for payload in items:
        if not payload.selected:
            continue
        slot = by_index.get(payload.slot_index)
        if not slot:
            raise BadRequestError(f"Unknown slot_index {payload.slot_index}.")

        # If payload carries detected_item_id, validate it matches the slot to catch any
        # frontend ordering bugs before they silently persist wrong image↔metadata pairs.
        payload_did = getattr(payload, "detected_item_id", None)
        if payload_did and by_detected_id:
            slot_did = slot.get("detected_item_id")
            if slot_did and payload_did != slot_did:
                logger.error(
                    "confirm_detected_item_id_mismatch",
                    slot_index=payload.slot_index,
                    slot_detected_item_id=slot_did,
                    payload_detected_item_id=payload_did,
                )
                raise BadRequestError(
                    f"detected_item_id mismatch for slot {payload.slot_index}: "
                    f"server has {slot_did!r}, client sent {payload_did!r}. "
                    "Re-run analyze-preview and try again."
                )

        # Image URLs come from the slot (server-side truth), not the payload.
        proc = str(slot.get("processed_image_url") or slot.get("crop_image_url") or slot["original_image_url"])
        orig = str(slot["original_image_url"])
        conf = slot.get("confidence_score")
        fabric = payload.fabric or payload.material

        logger.debug(
            "confirm_slot_image",
            slot_index=payload.slot_index,
            detected_item_id=slot.get("detected_item_id"),
            proc_url=proc,
            category=payload.category,
        )

        create = ClosetItemCreate(
            name=payload.name,
            category=payload.category,
            color=payload.color,
            fabric=fabric,
            pattern=payload.pattern,
            season=payload.season,
            occasion=payload.occasion,
            eco_score=payload.eco_score,
            tags=payload.tags,
            notes=payload.notes,
            brand=payload.brand,
            size=payload.size,
            fit=payload.fit,
            price=payload.price,
            image_url=proc,
            original_image_url=orig,
            processed_image_url=proc,
            background_removed=bool(slot.get("background_removed")),
            background_removal_status=slot.get("background_removal_status"),
            analysis_source="closet_preview_confirm",
            confidence_score=float(conf) if conf is not None else None,
            scan_batch_id=session.get("scan_id"),
        )
        saved.append(await create_item(user_id, create))

    await cache_service.delete(key)
    return saved
