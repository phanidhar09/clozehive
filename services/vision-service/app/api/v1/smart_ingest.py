"""
Smart bulk ingestion endpoints — /api/v1/smart-ingest/*

POST   /smart-ingest/                            Start a new ingest job
GET    /smart-ingest/{job_id}/status             Poll processing progress
GET    /smart-ingest/{job_id}/results            Fetch items pending review
PATCH  /smart-ingest/{job_id}/items/{item_id}    Edit a detected item's metadata
DELETE /smart-ingest/{job_id}/items/{item_id}    Reject / remove an item
POST   /smart-ingest/{job_id}/approve            Save approved items to closet
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.models.closet import ClosetItem
from app.schemas.closet import ClosetItemCreate
from app.services import bulk_ingest_service, cache_service, similarity_service
from app.services.upload_service import persist_upload, read_validated_image
from app.core.redis import get_redis

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
    status: str
    total_images: int
    processed_images: int
    items_detected: int
    failed_images: int
    created_at: str
    updated_at: str
    error: Optional[str] = None


class IngestResultsResponse(BaseModel):
    job_id: str
    status: str
    summary: dict[str, Any]
    items: list[dict[str, Any]]
    errors: list[str] = Field(default_factory=list)


class ItemUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    primary_color: Optional[str] = Field(None, max_length=100)
    secondary_colors: Optional[list[str]] = None
    pattern: Optional[str] = Field(None, max_length=100)
    material: Optional[str] = Field(None, max_length=100)
    occasion_tags: Optional[list[str]] = None
    season_tags: Optional[list[str]] = None
    style_tags: Optional[list[str]] = None
    fit: Optional[str] = Field(None, max_length=50)
    brand: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)


class ApproveRequest(BaseModel):
    item_ids: Optional[list[str]] = Field(
        None,
        description="IDs to approve. If omitted, all pending_review items are approved.",
    )


class ApproveResponse(BaseModel):
    approved: int
    failed: int
    closet_item_ids: list[str]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_job(job: dict[str, Any] | None, job_id: str) -> dict[str, Any]:
    """Raise 404 if job is missing or user mismatch."""
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
    and immediately return a job_id. The heavy AI work runs in a FastAPI BackgroundTask.
    """
    if len(files) > MAX_INGEST_FILES:
        raise BadRequestError(f"Maximum {MAX_INGEST_FILES} files per upload.")
    if len(files) == 0:
        raise BadRequestError("At least one file is required.")

    file_infos: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    for file in files:
        try:
            image_bytes, content_type = await read_validated_image(file)
            url = persist_upload(image_bytes, content_type, file.filename)
            from app.core.config import get_settings
            settings = get_settings()
            from pathlib import Path
            file_path = str(settings.upload_path / Path(url).name)

            file_infos.append({
                "filename": file.filename or f"image_{len(file_infos)}",
                "original_url": url,
                "file_path": file_path,
                "content_type": content_type,
            })
        except Exception as exc:
            validation_errors.append(f"{file.filename or 'unknown'}: {exc}")

    if not file_infos:
        raise BadRequestError(f"All files failed validation: {'; '.join(validation_errors)}")

    job_id = await bulk_ingest_service.create_job(user_id, len(file_infos))

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
        items=pending,
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
    """
    job = _require_job(
        await bulk_ingest_service.get_job_status(job_id, user_id),
        job_id,
    )
    all_items = await bulk_ingest_service.get_job_items(job_id, user_id) or []

    id_filter = set(body.item_ids) if body.item_ids else None
    to_approve = [
        i for i in all_items
        if i.get("status") == "pending_review"
        and (id_filter is None or i["temp_item_id"] in id_filter)
    ]

    if not to_approve:
        raise BadRequestError("No pending review items match the supplied IDs.")

    uid = UUID(user_id)

    created_ids: list[str] = []
    failed = 0

    for review_item in to_approve:
        try:
            item_create = ClosetItemCreate(
                name=review_item.get("name") or "Clothing Item",
                category=review_item.get("category", "other"),
                color=review_item.get("primary_color") or None,
                fabric=review_item.get("material") or None,
                pattern=review_item.get("pattern") or None,
                season=_pick_season(review_item.get("season_tags")),
                occasion=review_item.get("occasion_tags") or [],
                tags=_build_tags(review_item),
                image_url=review_item.get("processed_image_url") or review_item.get("original_crop_url"),
                notes=review_item.get("description") or None,
                brand=review_item.get("brand") or None,
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
            await session.flush()
            created_ids.append(str(new_item.id))

            background_tasks.add_task(
                similarity_service.update_item_embedding_job,
                str(new_item.id),
            )

        except Exception as exc:
            logger.error(
                "approve_item_failed",
                temp_id=review_item.get("temp_item_id"),
                error=str(exc),
            )
            failed += 1

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
    )


# ── Tiny helpers ───────────────────────────────────────────────────────────────

def _pick_season(season_tags: list[str] | None) -> list[str]:
    """Return recognised seasons from the AI tags list."""
    valid = {"spring", "summer", "fall", "winter"}
    result: list[str] = []
    seen: set[str] = set()
    for tag in (season_tags or []):
        mapped = "fall" if tag.lower() == "autumn" else tag.lower()
        if mapped in valid and mapped not in seen:
            result.append(mapped)
            seen.add(mapped)
    return result


def _build_tags(item: dict[str, Any]) -> list[str]:
    """Merge style_tags + subcategory into the closet_items.tags array."""
    tags: list[str] = []
    if item.get("subcategory"):
        tags.append(item["subcategory"])
    tags.extend(item.get("style_tags") or [])
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return result[:20]


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None
