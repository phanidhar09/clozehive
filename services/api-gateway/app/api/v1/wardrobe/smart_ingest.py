"""
Smart bulk ingestion endpoints  —  /api/v1/closet/smart-ingest/*

Endpoint map
------------
POST   /smart-ingest/                            Start a new ingest job
GET    /smart-ingest/{job_id}/status             Poll processing progress
GET    /smart-ingest/{job_id}/results            Fetch items pending review
PATCH  /smart-ingest/{job_id}/items/{item_id}    Edit a detected item's metadata
DELETE /smart-ingest/{job_id}/items/{item_id}    Reject / remove an item
POST   /smart-ingest/{job_id}/approve            Save approved items to closet

Security notes
--------------
• All endpoints require Bearer auth (CurrentUser).
• Every Redis read cross-checks user_id against the stored job owner.
  A user can never access another user's job even if they guess the job_id (UUID).
• Files are saved with UUID names; the upload directory is local (not user-path).

Why separate from closet.py
----------------------------
The smart-ingest flow is a multi-step async pipeline (upload → process →
review → approve) with its own state machine stored in Redis.  Mixing it
into the CRUD-focused closet.py would make both files harder to read.
Keeping it separate also makes it easy to disable/enable the feature
independently.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status
from pydantic import BaseModel, Field

from app.api.v1.wardrobe.schemas.closet import ClosetItemCreate
from app.api.v1.wardrobe.services import bulk_ingest_service, similarity_service
from app.api.v1.wardrobe.services.closet_similarity_service import check_similar_for_new_item
from app.core import cache_service
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.upload_service import persist_upload, read_validated_image, signed_url_for_stored
from app.models.closet import ClosetItem

# Keys in a review-item dict that may hold a stored GCS URL. Signed for outgoing
# responses only; the Redis job store keeps raw URLs (approve reads those).
_REVIEW_ITEM_URL_KEYS = (
    "processed_image_url",
    "original_crop_url",
    "original_image_url",
    "crop_image_url",
    "preview_image_url",
    "image_url",
)


def _sign_review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Swap stored GCS URLs for signed URLs on review items (response only).

    Safe to mutate: ``get_job_items`` returns fresh ``json.loads`` copies, so the
    Redis job store is untouched. No-op unless GCS_SIGNED_URLS is enabled.
    """
    for item in items:
        for key in _REVIEW_ITEM_URL_KEYS:
            if item.get(key):
                item[key] = signed_url_for_stored(item[key])
    return items


router = APIRouter(prefix="/smart-ingest", tags=["Smart Ingest"])
logger = get_logger("smart_ingest")

MAX_INGEST_FILES = 20


# ── Request / Response schemas ─────────────────────────────────────────────────


class IngestStartResponse(BaseModel):
    job_id: str
    status: str
    total_images: int
    message: str


class IngestStatusResponse(BaseModel):
    job_id: str
    status: str  # processing | completed | failed
    total_images: int
    processed_images: int
    items_detected: int
    failed_images: int
    created_at: str
    updated_at: str
    error: str | None = None


class IngestResultsResponse(BaseModel):
    job_id: str
    status: str
    summary: dict[str, Any]
    items: list[dict[str, Any]]
    errors: list[str] = Field(default_factory=list)


class ItemUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=255)
    category: str | None = Field(None, max_length=100)
    subcategory: str | None = Field(None, max_length=100)
    primary_color: str | None = Field(None, max_length=100)
    secondary_colors: list[str] | None = None
    pattern: str | None = Field(None, max_length=100)
    material: str | None = Field(None, max_length=100)
    occasion_tags: list[str] | None = None
    season_tags: list[str] | None = None
    style_tags: list[str] | None = None
    fit: str | None = Field(None, max_length=50)
    brand: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=1000)


class ApproveRequest(BaseModel):
    item_ids: list[str] | None = Field(
        None,
        description="IDs to approve. If omitted, all pending_review items are approved.",
    )


class SimilarItemWarning(BaseModel):
    """RAG-detected duplicate warning returned with the approval response."""

    new_item_name: str
    similar_item_id: str
    similar_item_name: str
    similarity_score: int
    similarity_reason: str


class ApproveResponse(BaseModel):
    approved: int
    failed: int
    closet_item_ids: list[str]
    similarity_warnings: list[SimilarItemWarning] = []


# ── Helpers ────────────────────────────────────────────────────────────────────


def _require_job(job: dict[str, Any] | None, job_id: str) -> dict[str, Any]:
    """Raise 404 if job is missing or user mismatch (service returns None for both)."""
    if job is None:
        raise NotFoundError(f"Ingest job {job_id} not found or access denied.")
    return job


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=IngestStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start AI bulk ingestion job",
)
async def start_ingest(
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> IngestStartResponse:
    """
    Accept up to 20 clothing images, save them to disk, create a Redis job,
    and immediately return a job_id.  The heavy AI work (Claude Vision +
    background removal) runs in a FastAPI BackgroundTask.

    Why return immediately (202)?
    Waiting for Claude Vision × 20 images synchronously would take 30-120 s
    and risk gateway timeouts.  Clients poll /status every 2 s instead.

    Why BackgroundTask instead of Kafka?
    The Kafka worker (ai-worker service) is for image events that come via
    the existing async upload flow.  Smart-ingest is a separate pipeline that
    runs entirely within the api-gateway process.  BackgroundTasks are simpler
    and avoid the Kafka round-trip for a user-facing interactive flow where
    the user is waiting for results.
    """
    if len(files) > MAX_INGEST_FILES:
        raise BadRequestError(f"Maximum {MAX_INGEST_FILES} files per upload.")
    if len(files) == 0:
        raise BadRequestError("At least one file is required.")

    # 1. Validate + persist all files before returning the response.
    #    We read bytes here because UploadFile objects are consumed by the
    #    request scope and cannot be safely referenced in a background task.
    file_infos: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    for file in files:
        try:
            image_bytes, content_type = await read_validated_image(file)
            url = await persist_upload(image_bytes, content_type, file.filename)
            from app.core.config import get_settings

            settings = get_settings()
            from pathlib import Path

            file_path = str(settings.upload_path / Path(url).name)

            file_infos.append(
                {
                    "filename": file.filename or f"image_{len(file_infos)}",
                    "original_url": url,
                    "file_path": file_path,
                    "content_type": content_type,
                }
            )
        except Exception as exc:
            validation_errors.append(f"{file.filename or 'unknown'}: {exc}")

    if not file_infos:
        raise BadRequestError(f"All files failed validation: {'; '.join(validation_errors)}")

    # 2. Create Redis job (returns job_id)
    job_id = await bulk_ingest_service.create_job(user_id, len(file_infos))

    # 3. Enqueue background processing
    background_tasks.add_task(
        bulk_ingest_service.process_job,
        job_id,
        user_id,
        file_infos,
    )

    logger.info(
        "smart_ingest_started",
        job_id=job_id,
        user_id=user_id,
        files=len(file_infos),
        rejected_at_validation=len(validation_errors),
    )

    return IngestStartResponse(
        job_id=job_id,
        status="processing",
        total_images=len(file_infos),
        message=f"Processing {len(file_infos)} image(s). Poll /status for progress.",
    )


@router.get(
    "/{job_id}/status",
    response_model=IngestStatusResponse,
    summary="Poll processing progress",
)
async def get_status(job_id: str, user_id: CurrentUser) -> IngestStatusResponse:
    """
    Returns current job state.  Poll every 2 s until status=='completed' or 'failed'.
    processed_images increments as each image finishes so the UI can show a
    real progress bar without a separate WebSocket connection.
    """
    job = _require_job(
        await bulk_ingest_service.get_job_status(job_id, user_id),
        job_id,
    )
    return IngestStatusResponse(**{k: job[k] for k in IngestStatusResponse.model_fields if k in job})


@router.get(
    "/{job_id}/results",
    response_model=IngestResultsResponse,
    summary="Get detected items for review",
)
async def get_results(job_id: str, user_id: CurrentUser) -> IngestResultsResponse:
    """
    Returns all detected items with status=pending_review.
    Call this once polling shows status==completed.
    """
    job = _require_job(
        await bulk_ingest_service.get_job_status(job_id, user_id),
        job_id,
    )
    items = await bulk_ingest_service.get_job_items(job_id, user_id) or []

    pending = [i for i in items if i.get("status") == "pending_review"]
    low_confidence = [i for i in pending if i.get("confidence_score", 1.0) < 0.70]

    return IngestResultsResponse(
        job_id=job_id,
        status=job["status"],
        summary={
            "total_images": job["total_images"],
            "items_detected": len(items),
            "items_ready_for_review": len(pending),
            "low_confidence_items": len(low_confidence),
            "failed_images": job.get("failed_images", 0),
        },
        items=_sign_review_items(pending),
    )


@router.patch(
    "/{job_id}/items/{item_id}",
    summary="Edit a detected item's metadata before approving",
)
async def update_item(
    job_id: str,
    item_id: str,
    body: ItemUpdateRequest,
    user_id: CurrentUser,
) -> dict[str, Any]:
    """
    Allows the user to correct AI-detected metadata (name, category, color…)
    in the review screen before committing to their closet.
    Only fields included in the request body are updated (partial update / PATCH semantics).
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise BadRequestError("No updatable fields provided.")

    updated = await bulk_ingest_service.update_item(job_id, item_id, user_id, updates)
    if updated is None:
        raise NotFoundError(f"Item {item_id} not found in job {job_id}.")
    return updated


@router.delete(
    "/{job_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reject / remove an incorrectly detected item",
)
async def reject_item(job_id: str, item_id: str, user_id: CurrentUser) -> None:
    """
    Marks the item as rejected.  Rejected items are excluded from /approve.
    The item remains in Redis (for auditing) but will not appear in /results.
    """
    removed = await bulk_ingest_service.reject_item(job_id, item_id, user_id)
    if not removed:
        raise NotFoundError(f"Item {item_id} not found in job {job_id}.")


@router.post(
    "/{job_id}/approve",
    response_model=ApproveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save approved items to closet",
)
async def approve_items(
    job_id: str,
    body: ApproveRequest,
    user_id: CurrentUser,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> ApproveResponse:
    """
    Writes approved ReviewItems into the closet_items table.

    If ``item_ids`` is omitted, every pending_review item is approved.
    Rejected items are always skipped.

    Post-save behaviour:
    • Closet cache is invalidated so the Closet page shows fresh data.
    • Embedding generation is enqueued as a background task per item.
    """
    _require_job(
        await bulk_ingest_service.get_job_status(job_id, user_id),
        job_id,
    )
    all_items = await bulk_ingest_service.get_job_items(job_id, user_id) or []

    # Filter: only pending_review; apply item_ids whitelist if supplied
    id_filter = set(body.item_ids) if body.item_ids else None
    to_approve = [
        i
        for i in all_items
        if i.get("status") == "pending_review" and (id_filter is None or i["temp_item_id"] in id_filter)
    ]

    if not to_approve:
        raise BadRequestError("No pending review items match the supplied IDs.")

    uid = UUID(user_id)

    created_ids: list[str] = []
    failed = 0
    similarity_warnings: list[SimilarItemWarning] = []

    for review_item in to_approve:
        try:
            # ── RAG duplicate pre-check ───────────────────────────────────────
            # Run a vector similarity check BEFORE saving so the user gets
            # warned about near-identical items they may already own.
            try:
                source_meta = {
                    "name": review_item.get("name") or "",
                    "category": review_item.get("category", "other"),
                    "color": review_item.get("primary_color") or "",
                    "material": review_item.get("material") or "",
                    "pattern": review_item.get("pattern") or "",
                }
                similar_items = await check_similar_for_new_item(
                    session, user_id, source_meta, limit=1, threshold_score=75
                )
                if similar_items:
                    top = similar_items[0]
                    similarity_warnings.append(
                        SimilarItemWarning(
                            new_item_name=source_meta["name"] or "New item",
                            similar_item_id=str(top.get("item_id") or top.get("id") or ""),
                            similar_item_name=top.get("name") or "",
                            similarity_score=int(top.get("similarity_score") or 0),
                            similarity_reason=top.get("similarity_reason") or "Similar item detected",
                        )
                    )
                    logger.info(
                        "ingest_duplicate_warning",
                        new_item=source_meta["name"],
                        similar_id=str(top.get("item_id") or top.get("id")),
                        score=top.get("similarity_score"),
                        user_id=user_id,
                    )
            except Exception as sim_exc:
                logger.debug("ingest_similarity_check_skipped", error=str(sim_exc))

            # Map review item → ClosetItemCreate
            item_create = ClosetItemCreate(
                name=review_item.get("name") or "Clothing Item",
                category=review_item.get("category", "other"),
                color=review_item.get("primary_color") or None,
                fabric=review_item.get("material") or None,
                pattern=review_item.get("pattern") or None,
                # Use the first matching season tag as the season field
                season=_pick_season(review_item.get("season_tags")),
                occasion=review_item.get("occasion_tags") or [],
                tags=_build_tags(review_item),
                # Store the processed (bg-removed) image as the primary image
                image_url=review_item.get("processed_image_url") or review_item.get("original_crop_url"),
                notes=review_item.get("description") or None,
                brand=review_item.get("brand") or None,
                # eco_score from AI
                eco_score=_safe_float(review_item.get("eco_score")),
            )

            new_item = ClosetItem(
                user_id=uid,
                name=item_create.name,
                category=item_create.category,
                color=item_create.color,
                fabric=item_create.fabric,
                pattern=item_create.pattern,
                season=item_create.season,
                occasion=item_create.occasion or [],
                eco_score=item_create.eco_score,
                tags=item_create.tags or [],
                image_url=item_create.image_url,
                notes=item_create.notes,
                brand=item_create.brand,
            )
            session.add(new_item)
            await session.flush()  # get the DB-assigned id
            created_ids.append(str(new_item.id))

            await similarity_service.schedule_embedding_update(background_tasks, str(new_item.id))

        except Exception as exc:
            logger.error(
                "approve_item_failed",
                temp_id=review_item.get("temp_item_id"),
                error=str(exc),
            )
            failed += 1

    # Request-scoped session commits in get_session; do not commit here.

    # Invalidate AI suggestion cache and all closet list pages so the UI reloads
    redis = await get_redis()
    await cache_service.invalidate_user_ai_cache(redis, user_id)
    await cache_service.invalidate_closet_list_cache(user_id)

    logger.info(
        "smart_ingest_approved",
        job_id=job_id,
        user_id=user_id,
        approved=len(created_ids),
        failed=failed,
    )

    return ApproveResponse(
        approved=len(created_ids),
        failed=failed,
        closet_item_ids=created_ids,
        similarity_warnings=similarity_warnings,
    )


# ── Tiny helpers ───────────────────────────────────────────────────────────────


def _pick_season(season_tags: list[str] | None) -> str | None:
    """Pick the first recognised season from the AI tags list."""
    valid = {"spring", "summer", "fall", "winter", "autumn"}
    for tag in season_tags or []:
        if tag.lower() in valid:
            # Normalise autumn → fall for consistency with existing schema
            return "fall" if tag.lower() == "autumn" else tag.lower()
    return None


def _build_tags(item: dict[str, Any]) -> list[str]:
    """Merge style_tags + subcategory into the closet_items.tags array."""
    tags: list[str] = []
    if item.get("subcategory"):
        tags.append(item["subcategory"])
    tags.extend(item.get("style_tags") or [])
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return result[:20]  # closet schema allows max 20 tags


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
