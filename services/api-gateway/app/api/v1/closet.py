"""
Closet routes — /api/v1/closet/*
Full CRUD + wear logging + AI vision upload.
Data stored in PostgreSQL via ClosetService.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Any, cast

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.core.deps import CurrentUser
from app.db.session import get_session
from app.constants.wardrobe import CLOSET_SECTIONS
from app.core.exceptions import BadRequestError
from app.events import producer as event_producer, topics
from app.events.schemas import AsyncAcceptedResponse, EventEnvelope
from app.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
    ClosetUploadResponse,
    LogWearRequest,
)
from app.services import cache_service, similarity_service, vision_service
from app.services.ai_request_service import create_request
from app.services.closet_service import ClosetService
from app.services.upload_service import persist_upload, read_validated_image

router = APIRouter(prefix="/closet", tags=["Closet"])
settings = get_settings()

MAX_BULK_UPLOAD_FILES = 20


class BulkUploadFailure(BaseModel):
    filename: str
    error: str


class BulkUploadResponse(BaseModel):
    created: list[ClosetItemResponse] = Field(default_factory=list)
    failed: list[BulkUploadFailure] = Field(default_factory=list)


def _normalise_category(category: Optional[str]) -> str:
    if not category:
        return "uncategorised"
    return category.strip().lower()


def _item_from_vision(
    vision: dict[str, Any],
    image_url: str,
    name: Optional[str] = None,
    category: Optional[str] = None,
) -> ClosetItemCreate:
    return ClosetItemCreate(
        name=name or str(vision.get("name") or "Clothing Item"),
        category=_normalise_category(
            category or (str(vision["category"]) if vision.get("category") else None)
        ),
        color=str(vision["color"]) if vision.get("color") else None,
        fabric=str(vision["material"]) if vision.get("material") else None,
        pattern=str(vision["pattern"]) if vision.get("pattern") else None,
        season=vision.get("season"),  # schema validator normalises str/list → list[str]
        occasion=list(vision["occasion"]) if isinstance(vision.get("occasion"), list) else [],
        eco_score=float(vision["eco_score"]) if vision.get("eco_score") is not None else None,
        tags=list(vision["tags"]) if isinstance(vision.get("tags"), list) else None,
        image_url=image_url,
        notes=str(vision["notes"]) if vision.get("notes") else None,
        brand=str(vision["brand"]) if vision.get("brand") else None,
    )


async def _analyse_file(file: UploadFile) -> tuple[str, dict[str, Any]]:
    image_bytes, content_type = await read_validated_image(file)
    image_url = persist_upload(image_bytes, content_type, file.filename)
    raw = await vision_service.analyze_image(image_bytes, content_type)
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
    per_page: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
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
async def get_item(user_id: CurrentUser, item_id: UUID, session: AsyncSession = Depends(get_session)):
    svc = _get_svc(session)
    return await svc.get_item(item_id, UUID(user_id))


@router.get("/{item_id}/similar", response_model=list[ClosetItemResponse])
async def get_similar_items(user_id: CurrentUser, item_id: UUID, session: AsyncSession = Depends(get_session)):
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
    background_tasks.add_task(similarity_service.update_item_embedding, session, str(item.id))
    return item


@router.post(
    "/upload",
    response_model=ClosetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload garment image + auto-detect attributes via AI Vision",
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

    image_url = persist_upload(image_bytes, content_type, file.filename)

    vision: dict = {}
    try:
        raw = await vision_service.analyze_image(image_bytes, content_type)
        vision = raw if isinstance(raw, dict) else {}
    except Exception:
        vision = {}

    item_data = _item_from_vision(vision, image_url, name=name, category=category)

    svc = _get_svc(session)
    item = await svc.create_item(UUID(user_id), item_data)
    await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
    background_tasks.add_task(similarity_service.update_item_embedding, session, str(item.id))
    return ClosetUploadResponse(item=item, vision_analysis=vision)


@router.post(
    "/bulk-upload",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and analyse up to 20 garment images",
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
            background_tasks.add_task(similarity_service.update_item_embedding, session, str(item.id))
        except Exception as exc:
            failed.append(BulkUploadFailure(filename=filename, error=str(exc)))

    if created:
        await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)
    return BulkUploadResponse(created=created, failed=failed)


@router.post(
    "/upload/async",
    response_model=AsyncAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload garment image and queue async AI Vision analysis",
)
async def upload_item_async(
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),  # Postgres session only needed for create_request
    file: UploadFile = File(...),
    name: Optional[str] = None,
    category: Optional[str] = None,
):
    image_bytes, content_type = await read_validated_image(file)

    request_id = uuid4()
    upload_id = uuid4()
    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    upload_path = settings.upload_path / f"{upload_id}{suffix}"
    upload_path.write_bytes(image_bytes)

    user_uuid = UUID(user_id)
    payload = {
        "upload_id": str(upload_id),
        "file_path": str(upload_path),
        "media_type": content_type,
        "original_filename": file.filename,
        "name_override": name,
        "category_override": category,
    }
    await create_request(
        session,
        request_id=request_id,
        user_id=user_uuid,
        request_type=topics.IMAGE_UPLOADED,
        input_payload=payload,
    )
    await session.commit()
    await event_producer.publish(
        topics.IMAGE_UPLOADED,
        EventEnvelope(
            event_type=topics.IMAGE_UPLOADED,
            request_id=request_id,
            user_id=user_uuid,
            payload=payload,
        ),
    )
    return AsyncAcceptedResponse(
        request_id=request_id,
        event_type=topics.IMAGE_UPLOADED,
        message="Image analysis queued",
    )


# ── Update / delete ───────────────────────────────────────────────────────────

@router.patch("/{item_id}", response_model=ClosetItemResponse)
async def update_item(item_id: UUID, body: ClosetItemUpdate, user_id: CurrentUser, session: AsyncSession = Depends(get_session)):
    svc = _get_svc(session)
    item = await svc.update_item(item_id, UUID(user_id), body)
    await similarity_service.update_item_embedding(session, str(item.id))
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, user_id: CurrentUser, session: AsyncSession = Depends(get_session)):
    svc = _get_svc(session)
    await svc.delete_item(item_id, UUID(user_id))
    await cache_service.invalidate_user_ai_cache(await get_redis(), user_id)


# ── Wear log ──────────────────────────────────────────────────────────────────

@router.post("/{item_id}/wear", response_model=ClosetItemResponse)
async def log_wear(item_id: UUID, body: LogWearRequest, user_id: CurrentUser, session: AsyncSession = Depends(get_session)):
    svc = _get_svc(session)
    return await svc.log_wear(item_id, UUID(user_id), body.worn_date)
