"""
Closet routes — /api/v1/closet/*
Full CRUD + wear logging + AI vision upload.
Data stored in PostgreSQL via ClosetService.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Any, cast

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.core.deps import CurrentUser
from app.core.rate_limit import limiter
from app.db.session import get_read_session, get_session
from app.constants.wardrobe import CLOSET_SECTIONS
from app.core.exceptions import BadRequestError
from app.api.v1.wardrobe.schemas.closet import (
    BulkAnalyzePreviewFileResult,
    BulkAnalyzePreviewResponse,
    BulkPreviewFailure,
    ClosetAnalyzePreviewResponse,
    ClosetConfirmRequest,
    ClosetConfirmResponse,
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
    ClosetUploadResponse,
    LogWearRequest,
    coerce_closet_category,
)
from app.core.logging import get_logger
from app.api.v1.wardrobe.services import closet_preview_service, similarity_service, vision_service
from app.core import cache_service

_log = get_logger("closet_routes")
from app.api.v1.intelligence.services.ai_request_service import create_request
from app.api.v1.wardrobe.services.closet_service import ClosetService
import asyncio

from app.core.upload_service import delete_upload, persist_upload, read_validated_image

# Hard cap for any vision-service / OpenAI vision call.  Without this a
# hanging upstream can block a worker process indefinitely.
_VISION_TIMEOUT_S: float = 30.0

# Lazy import to avoid circular dependency — ws.manager is only accessed inside functions
def _ws_push(user_id: str, data: dict) -> None:
    """Fire-and-forget WebSocket push — never raises but always logs on failure."""
    try:
        import asyncio
        from app.api.v1.platform.ws import manager as _ws_manager
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_ws_manager.broadcast_to_user(user_id, data))
    except Exception as exc:  # noqa: BLE001
        _log.warning("ws_push_failed", user_id=user_id, event=data.get("type"), error=str(exc))


router = APIRouter(prefix="/closet", tags=["Closet"])
settings = get_settings()

MAX_BULK_UPLOAD_FILES = 20


class BulkUploadFailure(BaseModel):
    filename: str
    error: str


class BulkUploadResponse(BaseModel):
    created: list[ClosetItemResponse] = Field(default_factory=list)
    failed: list[BulkUploadFailure] = Field(default_factory=list)


def _occasion_from_vision(vision: dict[str, Any]) -> list[str]:
    occ = vision.get("occasion")
    if isinstance(occ, list) and occ:
        return [str(x) for x in occ if x]
    occ = vision.get("occasions")
    if isinstance(occ, list) and occ:
        return [str(x) for x in occ if x]
    return []


def _notes_from_vision(vision: dict[str, Any]) -> str | None:
    n = vision.get("notes")
    if n is not None and str(n).strip():
        return str(n).strip()
    d = vision.get("description")
    if d is not None and str(d).strip():
        return str(d).strip()
    return None


def _item_from_vision(
    vision: dict[str, Any],
    image_url: str,
    name: Optional[str] = None,
    category: Optional[str] = None,
) -> ClosetItemCreate:
    garment_notes = _notes_from_vision(vision)
    return ClosetItemCreate(
        name=name or str(vision.get("name") or "Clothing Item"),
        category=coerce_closet_category(
            category or (str(vision["category"]) if vision.get("category") else None)
        ),
        color=str(vision["color"]) if vision.get("color") else None,
        fabric=str(vision["material"]) if vision.get("material") else None,
        pattern=str(vision["pattern"]) if vision.get("pattern") else None,
        season=vision.get("season"),  # schema validator normalises str/list → list[str]
        occasion=_occasion_from_vision(vision) or None,
        eco_score=float(vision["eco_score"]) if vision.get("eco_score") is not None else None,
        tags=list(vision["tags"]) if isinstance(vision.get("tags"), list) else None,
        image_url=image_url,
        notes=garment_notes,
        brand=str(vision["brand"]) if vision.get("brand") else None,
    )


async def _analyse_file(file: UploadFile) -> tuple[str, dict[str, Any]]:
    image_bytes, content_type = await read_validated_image(file)
    image_url = await persist_upload(image_bytes, content_type, file.filename)
    try:
        raw = await asyncio.wait_for(
            vision_service.analyze_image(image_bytes, content_type),
            timeout=_VISION_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        _log.warning("vision_analysis_timeout", filename=file.filename, timeout=_VISION_TIMEOUT_S)
        raw = {}
    vision = raw if isinstance(raw, dict) else {}
    return image_url, vision


def _get_svc(session: AsyncSession) -> ClosetService:
    return ClosetService(session)


# ── List / get ────────────────────────────────────────────────────────────────

@router.get("/", response_model=ClosetListResponse)
async def list_items(
    user_id: CurrentUser,
    section: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_read_session),
):
    if section is not None and section not in CLOSET_SECTIONS:
        raise BadRequestError("Invalid section filter.")
    svc = _get_svc(session)
    return await svc.list_items(
        UUID(user_id),
        section=section,
        category=category,
        season=season,
        page=page,
        per_page=per_page,
    )


@router.get("/{item_id}", response_model=ClosetItemResponse)
async def get_item(user_id: CurrentUser, item_id: UUID, session: AsyncSession = Depends(get_read_session)):
    svc = _get_svc(session)
    return await svc.get_item(item_id, UUID(user_id))


@router.get("/{item_id}/similar", response_model=list[ClosetItemResponse])
async def get_similar_items(user_id: CurrentUser, item_id: UUID, session: AsyncSession = Depends(get_read_session)):
    return await similarity_service.find_similar_items(session, str(item_id), user_id, limit=5)


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ClosetItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    user_id: CurrentUser,
    body: ClosetItemCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    item = await svc.create_item(UUID(user_id), body)
    await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
    await similarity_service.schedule_embedding_update(background_tasks, str(item.id))
    # Real-time push: notify the user's open browser tabs that a new item was added
    background_tasks.add_task(_ws_push, user_id, {
        "type": "notification",
        "channel": "closet",
        "data": {"event": "item_added", "item_name": item.name, "category": item.category},
    })
    return item


@router.post(
    "/analyze-preview",
    response_model=ClosetAnalyzePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze image and stage a preview session (no closet row yet)",
)
@limiter.limit("10/minute")
async def analyze_preview_endpoint(
    request: Request,
    user_id: CurrentUser,
    file: UploadFile = File(...),
):
    image_bytes, content_type = await read_validated_image(file)
    return await closet_preview_service.analyze_preview(
        UUID(user_id),
        image_bytes=image_bytes,
        content_type=content_type,
        filename=file.filename,
    )


@router.post(
    "/confirm",
    response_model=ClosetConfirmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Persist selected preview slots as closet items",
)
async def confirm_closet_preview(
    user_id: CurrentUser,
    body: ClosetConfirmRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    saved = await closet_preview_service.confirm_preview(
        UUID(user_id),
        preview_session_id=body.preview_session_id,
        items=body.items,
        create_item=svc.create_item,
    )
    if saved:
        await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
        for item in saved:
            await similarity_service.schedule_embedding_update(background_tasks, str(item.id))
    return ClosetConfirmResponse(saved=saved, total_saved=len(saved))


@router.post(
    "/bulk-analyze-preview",
    response_model=BulkAnalyzePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze up to 20 images — each file returns its own preview session",
)
@limiter.limit("5/minute")
async def bulk_analyze_preview(
    request: Request,
    user_id: CurrentUser,
    files: list[UploadFile] = File(...),
):
    if len(files) > MAX_BULK_UPLOAD_FILES:
        raise BadRequestError("Maximum 20 files per bulk upload.")

    user_uuid = UUID(user_id)
    results: list[BulkAnalyzePreviewFileResult] = []
    failed: list[BulkPreviewFailure] = []

    for file in files:
        filename = file.filename or "upload"
        try:
            image_bytes, content_type = await read_validated_image(file)
            preview = await closet_preview_service.analyze_preview(
                user_uuid,
                image_bytes=image_bytes,
                content_type=content_type,
                filename=file.filename,
            )
            results.append(BulkAnalyzePreviewFileResult(filename=filename, preview=preview))
        except Exception as exc:
            failed.append(BulkPreviewFailure(filename=filename, error=str(exc)))

    return BulkAnalyzePreviewResponse(results=results, failed=failed)


@router.post(
    "/upload",
    response_model=ClosetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Legacy] Upload garment image + auto-save after AI Vision",
    deprecated=True,
    description=(
        "Creates a `closet_items` row immediately. Prefer `POST /closet/analyze-preview` "
        "followed by `POST /closet/confirm` so users can review before saving."
    ),
)
async def upload_item(
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    name: Optional[str] = None,
    category: Optional[str] = None,
):
    image_bytes, content_type = await read_validated_image(file)

    image_url = await persist_upload(image_bytes, content_type, file.filename)

    vision: dict = {}
    try:
        raw = await asyncio.wait_for(
            vision_service.analyze_image(image_bytes, content_type),
            timeout=_VISION_TIMEOUT_S,
        )
        vision = raw if isinstance(raw, dict) else {}
    except asyncio.TimeoutError:
        _log.warning("vision_upload_timeout", timeout=_VISION_TIMEOUT_S)
        vision = {}
    except Exception:
        vision = {}

    item_data = _item_from_vision(vision, image_url, name=name, category=category)

    svc = _get_svc(session)
    item = await svc.create_item(UUID(user_id), item_data)
    await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
    await similarity_service.schedule_embedding_update(background_tasks, str(item.id))
    return ClosetUploadResponse(item=item, vision_analysis=vision)


@router.post(
    "/bulk-upload",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Legacy] Upload and auto-save up to 20 garment images",
    deprecated=True,
    description=(
        "Creates rows immediately per file. Prefer `POST /closet/bulk-analyze-preview` "
        "then `POST /closet/confirm` per staged session."
    ),
)
async def bulk_upload_items(
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
):
    if len(files) > MAX_BULK_UPLOAD_FILES:
        raise BadRequestError("Maximum 20 files per bulk upload.")

    results = await asyncio.gather(*(_analyse_file(file) for file in files), return_exceptions=True)
    svc = _get_svc(session)
    created: list[ClosetItemResponse] = []
    failed: list[BulkUploadFailure] = []
    user_uuid = UUID(user_id)

    for file, result in zip(files, results):
        filename = file.filename or "upload"
        if isinstance(result, Exception):
            failed.append(BulkUploadFailure(filename=filename, error=str(result)))
            continue

        image_url, vision = cast(tuple[Any, Any], result)
        try:
            item = await svc.create_item(user_uuid, _item_from_vision(vision, image_url))
            created.append(item)
            await similarity_service.schedule_embedding_update(background_tasks, str(item.id))
        except Exception as exc:
            failed.append(BulkUploadFailure(filename=filename, error=str(exc)))

    if created:
        await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
    return BulkUploadResponse(created=created, failed=failed)


# ── Update / delete ───────────────────────────────────────────────────────────

@router.patch("/{item_id}", response_model=ClosetItemResponse)
async def update_item(
    item_id: UUID,
    body: ClosetItemUpdate,
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    item = await svc.update_item(item_id, UUID(user_id), body)
    # Recompute the embedding off the request path. Doing it inline blocked the
    # response for the full OpenAI round-trip, and any embedding error rolled
    # back the metadata update too — silently losing the user's edit.
    await similarity_service.schedule_embedding_update(background_tasks, str(item.id))
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    image_urls = await svc.delete_item(item_id, UUID(user_id))
    await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
    # Clean up stored blobs after the DB row is gone — best-effort, non-blocking
    for url in image_urls:
        background_tasks.add_task(delete_upload, url)


# ── Wear log ──────────────────────────────────────────────────────────────────

@router.post("/{item_id}/wear", response_model=ClosetItemResponse)
async def log_wear(item_id: UUID, body: LogWearRequest, user_id: CurrentUser, session: AsyncSession = Depends(get_session)):
    svc = _get_svc(session)
    return await svc.log_wear(item_id, UUID(user_id), body.worn_date)


# ── Re-embed all items ────────────────────────────────────────────────────────

@router.post("/re-embed", status_code=status.HTTP_202_ACCEPTED)
async def re_embed_closet(
    user_id: CurrentUser,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    force: bool = Query(False, description="Re-embed even items that already have an embedding"),
):
    """
    Regenerate embeddings for all closet items owned by the current user.

    **Must be called after:**
    - Upgrading the embedding model (e.g. ada-002 → text-embedding-3-small)
    - Changing item_to_embedding_text() to include additional fields

    Runs in the background; returns immediately with a task summary.
    Embeddings are updated in batches of 20 with a small delay to avoid
    rate-limiting the OpenAI Embeddings API.
    """
    from sqlalchemy import text as sql_text
    from app.api.v1.wardrobe.services.similarity_service import generate_item_embedding
    from app.models.closet import ClosetItem
    from sqlalchemy import select

    # Count items first (fast)
    count_sql = sql_text(
        "SELECT COUNT(*) FROM closet_items WHERE user_id = CAST(:uid AS uuid) AND is_archived = false"
        + ("" if force else " AND embedding IS NULL")
    )
    count_result = await session.execute(count_sql, {"uid": user_id})
    total = count_result.scalar() or 0

    async def _run_re_embed(uid: str, do_force: bool) -> None:
        """Background task: batch re-embed all user's items."""
        import asyncio
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as bg_session:
            stmt = select(ClosetItem).where(
                ClosetItem.user_id == UUID(uid),
                ClosetItem.is_archived.is_(False),
            )
            if not do_force:
                stmt = stmt.where(ClosetItem.embedding.is_(None))

            result = await bg_session.execute(stmt)
            items = result.scalars().all()

            succeeded = 0
            failed = 0
            for i, item in enumerate(items):
                try:
                    item.embedding = await generate_item_embedding(item)
                    succeeded += 1
                except Exception as exc:
                    failed += 1
                    import logging
                    logging.getLogger("re_embed").warning(
                        "re_embed_item_failed", item_id=str(item.id), error=str(exc)
                    )
                # Commit in batches of 20
                if (i + 1) % 20 == 0:
                    await bg_session.commit()
                    await asyncio.sleep(0.3)   # brief pause for API rate limits

            await bg_session.commit()

    background_tasks.add_task(_run_re_embed, user_id, force)

    return {
        "status": "started",
        "items_queued": total,
        "force": force,
        "message": (
            f"Re-embedding {total} item(s) in the background. "
            "New similarity searches will reflect the updated embeddings once complete."
        ),
    }
