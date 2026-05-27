"""
Smart bulk ingestion pipeline for ClozeHive.

Flow
----
1. Client POSTs N images  →  API saves to disk, creates Redis job, returns job_id
   immediately (202-style fast response).
2. FastAPI BackgroundTask calls ``process_job()`` which:
      for each image:
        a. Load bytes from disk
        b. Call vision_service.analyze_for_bulk()  (OpenAI vision)
        c. Call background_removal_service.remove_background()  (PIL)
        d. persist_upload() the processed PNG
        e. Build a ReviewItem record → append to Redis
        f. Update job progress counter in Redis
3. Client polls GET /status until status=="completed".
4. Client GETs /results  →  ReviewItems with status=pending_review.
5. Client edits / rejects items via PATCH/DELETE.
6. Client POSTs /approve with selected item IDs  →  API writes to closet_items table.

Redis schema
------------
Key  ``clozehive:ingest:{job_id}``       TTL 86 400 s (24 h)
Value  JSON blob (IngestJob model)

Key  ``clozehive:ingest:{job_id}:items`` TTL 86 400 s (24 h)
Value  JSON array of ReviewItem dicts

Why Redis instead of a new DB table
------------------------------------
Ingest jobs are ephemeral — users review and approve within hours, not months.
Redis provides:
  • Built-in TTL (auto-cleanup, no cron job needed)
  • No Alembic migration required
  • O(1) reads for status polling
  • Atomic GETSET for progress updates
Only the final approved items cross into PostgreSQL (closet_items).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.services import vision_service
from app.services.background_removal_service import remove_background
from app.services.upload_service import persist_upload, read_upload_bytes

logger = get_logger("bulk_ingest_service")

_JOB_TTL = 86_400        # 24 h — enough for any review session
_ITEM_REVIEW_TTL = 86_400

_JOB_KEY = "clozehive:ingest:{}"
_ITEMS_KEY = "clozehive:ingest:{}:items"


# ── Pydantic-free data models (dicts serialised to/from Redis JSON) ───────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_job(
    job_id: str,
    user_id: str,
    total_images: int,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "user_id": user_id,
        "status": "processing",          # pending | processing | completed | failed
        "total_images": total_images,
        "processed_images": 0,
        "items_detected": 0,
        "failed_images": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
    }


def make_review_item(
    job_id: str,
    source_filename: str,
    original_url: str,
    processed_url: str,
    vision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "temp_item_id": str(uuid.uuid4()),
        "job_id": job_id,
        "source_image_id": source_filename,
        "original_crop_url": original_url,
        "processed_image_url": processed_url,
        # ── AI-generated fields ───────────────────────────────────────────────
        "name": vision.get("name") or "Clothing Item",
        "category": _normalise_category(vision.get("category")),
        "subcategory": vision.get("subcategory") or "",
        "description": vision.get("description") or "",
        "primary_color": vision.get("primary_color") or vision.get("color") or "",
        "secondary_colors": vision.get("secondary_colors") or [],
        "pattern": vision.get("pattern") or "",
        "material": vision.get("material") or "",
        "occasion_tags": vision.get("occasion_tags") or vision.get("occasion") or [],
        "season_tags": vision.get("season_tags") or [],
        "style_tags": vision.get("style_tags") or [],
        "fit": vision.get("fit") or "Regular",
        "eco_score": vision.get("eco_score"),
        "brand": vision.get("brand") or "",
        "confidence_score": float(vision.get("confidence_score") or vision.get("confidence") or 0.0),
        # ── Review state ──────────────────────────────────────────────────────
        "status": "pending_review",      # pending_review | approved | rejected
        "needs_review": float(vision.get("confidence_score") or 0.0) < 0.70,
        "warnings": list(vision.get("warnings") or []),
    }


def _normalise_category(raw: Any) -> str:
    """Coerce AI-returned category to the canonical set used by closet_items."""
    allowed = {"tops", "bottoms", "shoes", "outerwear", "dresses", "accessories", "other"}
    # Common alias mappings the LLM might use
    aliases = {
        "footwear": "shoes",
        "sneakers": "shoes",
        "bags": "accessories",
        "jewelry": "accessories",
        "jewellery": "accessories",
        "socks": "other",
        "inners": "other",
        "basics": "tops",
        "shirt": "tops",
        "pants": "bottoms",
        "trousers": "bottoms",
        "jeans": "bottoms",
    }
    cat = str(raw or "other").strip().lower()
    if cat in allowed:
        return cat
    if cat in aliases:
        return aliases[cat]
    # Try prefix match
    for allowed_cat in allowed:
        if allowed_cat.startswith(cat[:4]):
            return allowed_cat
    return "other"


# ── Redis helpers ──────────────────────────────────────────────────────────────

async def _get_job(redis: Any, job_id: str) -> dict[str, Any] | None:
    raw = await redis.get(_JOB_KEY.format(job_id))
    return json.loads(raw) if raw else None


async def _set_job(redis: Any, job: dict[str, Any]) -> None:
    job["updated_at"] = _now_iso()
    await redis.set(
        _JOB_KEY.format(job["job_id"]),
        json.dumps(job),
        ex=_JOB_TTL,
    )


async def _get_items(redis: Any, job_id: str) -> list[dict[str, Any]]:
    raw = await redis.get(_ITEMS_KEY.format(job_id))
    return json.loads(raw) if raw else []


async def _set_items(redis: Any, job_id: str, items: list[dict[str, Any]]) -> None:
    await redis.set(
        _ITEMS_KEY.format(job_id),
        json.dumps(items),
        ex=_ITEM_REVIEW_TTL,
    )


# ── Job lifecycle ──────────────────────────────────────────────────────────────

async def create_job(user_id: str, total_images: int) -> str:
    """
    Create a new ingest job in Redis and return the job_id.
    Called synchronously before spawning the background task.
    """
    job_id = str(uuid.uuid4())
    redis = await get_redis()
    job = make_job(job_id, user_id, total_images)
    await _set_job(redis, job)
    await _set_items(redis, job_id, [])
    logger.info("ingest_job_created", job_id=job_id, total_images=total_images)
    return job_id


async def get_job_status(job_id: str, user_id: str) -> dict[str, Any] | None:
    """Return job dict if it belongs to the requesting user, else None."""
    redis = await get_redis()
    job = await _get_job(redis, job_id)
    if job and job.get("user_id") == user_id:
        return job
    return None


async def get_job_items(job_id: str, user_id: str) -> list[dict[str, Any]] | None:
    """Return items list if the job belongs to the requesting user, else None."""
    redis = await get_redis()
    job = await _get_job(redis, job_id)
    if not job or job.get("user_id") != user_id:
        return None
    return await _get_items(redis, job_id)


async def update_item(
    job_id: str,
    item_id: str,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Patch a single review item; returns updated item or None if not found."""
    redis = await get_redis()
    job = await _get_job(redis, job_id)
    if not job or job.get("user_id") != user_id:
        return None
    items = await _get_items(redis, job_id)
    for i, item in enumerate(items):
        if item["temp_item_id"] == item_id:
            allowed_keys = {
                "name", "category", "subcategory", "primary_color",
                "secondary_colors", "pattern", "material",
                "occasion_tags", "season_tags", "style_tags", "fit",
                "brand", "description",
            }
            for k, v in updates.items():
                if k in allowed_keys:
                    items[i][k] = v
            await _set_items(redis, job_id, items)
            return items[i]
    return None


async def reject_item(job_id: str, item_id: str, user_id: str) -> bool:
    """Mark an item as rejected; returns True if found and updated."""
    redis = await get_redis()
    job = await _get_job(redis, job_id)
    if not job or job.get("user_id") != user_id:
        return False
    items = await _get_items(redis, job_id)
    for i, item in enumerate(items):
        if item["temp_item_id"] == item_id:
            items[i]["status"] = "rejected"
            await _set_items(redis, job_id, items)
            return True
    return False


# ── Background processing pipeline ────────────────────────────────────────────

async def process_job(
    job_id: str,
    user_id: str,
    file_infos: list[dict[str, Any]],
) -> None:
    """
    Background task that processes each uploaded image through the full pipeline:
      1. Load from disk
      2. Analyse with Claude Vision (analyze_for_bulk)
      3. Remove background (PIL)
      4. Persist processed PNG
      5. Build ReviewItem → append to Redis
      6. Update job progress

    Never raises — all per-image errors are caught so the job continues.
    The job status is always set to 'completed' or 'failed' when done.
    """
    redis = await get_redis()
    job = await _get_job(redis, job_id)
    if not job:
        logger.error("ingest_job_not_found_in_background", job_id=job_id)
        return

    items: list[dict[str, Any]] = []

    for idx, info in enumerate(file_infos):
        filename = info.get("filename") or f"image_{idx}"
        original_url = info["original_url"]
        file_path = info["file_path"]
        content_type = info.get("content_type", "image/jpeg")

        logger.info(
            "ingest_processing_image",
            job_id=job_id,
            index=idx + 1,
            total=len(file_infos),
            filename=filename,
        )

        try:
            # 1. Load raw bytes from GCS or local disk
            raw_bytes = await asyncio.to_thread(read_upload_bytes, original_url)

            # 2. Claude Vision analysis (async)
            vision = await vision_service.analyze_for_bulk(raw_bytes, content_type)

            # 3. Remove background (sync, PIL — fast for typical ~1 MB images)
            processed_bytes = remove_background(raw_bytes)

            # 4. Persist processed PNG (background-removed version)
            processed_url = await persist_upload(
                processed_bytes,
                "image/png",
                f"processed_{filename}",
            )

            # 5. Build review item
            item = make_review_item(
                job_id=job_id,
                source_filename=filename,
                original_url=original_url,
                processed_url=processed_url,
                vision=vision,
            )
            items.append(item)

            # 6. Update Redis items immediately so the UI can show progress
            await _set_items(redis, job_id, items)

        except Exception as exc:
            logger.error(
                "ingest_image_failed",
                job_id=job_id,
                filename=filename,
                error=str(exc),
            )
            job["failed_images"] = job.get("failed_images", 0) + 1

        # Update processed counter
        job["processed_images"] = idx + 1
        job["items_detected"] = len(items)
        await _set_job(redis, job)

    # Mark job complete
    job["status"] = "completed"
    job["items_detected"] = len(items)
    await _set_job(redis, job)

    logger.info(
        "ingest_job_completed",
        job_id=job_id,
        items_detected=len(items),
        failed=job.get("failed_images", 0),
    )
