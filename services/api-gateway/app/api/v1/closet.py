"""
Closet routes — /api/v1/closet/*
Full CRUD + wear logging + AI vision upload.
Data stored in Firestore; only async AI-request tracking still uses Postgres.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
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
from app.services import ai_client
from app.services.ai_request_service import create_request
from app.services.firestore.closet_service import FirestoreClosetService

router = APIRouter(prefix="/closet", tags=["Closet"])
settings = get_settings()

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_MAX_UPLOAD_MB = 10
_UPLOAD_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

_ALLOWED_SECTIONS = frozenset({
    "clothing", "accessories", "shoes", "outerwear",
    "dresses", "inners", "special_occasion",
})


def _persist_upload(image_bytes: bytes, content_type: str, filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
        suffix = _UPLOAD_EXTENSIONS.get(content_type, ".jpg")
    stored_name = f"{uuid4()}{suffix}"
    (settings.upload_path / stored_name).write_bytes(image_bytes)
    return f"/uploads/{stored_name}"


def _normalise_category(category: str | None) -> str:
    if not category:
        return "uncategorised"
    return category.strip().lower()


def _get_svc() -> FirestoreClosetService:
    return FirestoreClosetService()


# ── List / get ────────────────────────────────────────────────────────────────

@router.get("/", response_model=ClosetListResponse)
async def list_items(
    user_id: CurrentUser,
    section: str | None = Query(None),
    category: str | None = Query(None),
    season: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    svc = _get_svc()
    return await svc.list_items(
        UUID(user_id),
        section=section,
        category=category,
        season=season,
        page=page,
        per_page=per_page,
    )


@router.get("/{item_id}", response_model=ClosetItemResponse)
async def get_item(item_id: UUID, user_id: CurrentUser):
    svc = _get_svc()
    return await svc.get_item(item_id, UUID(user_id))


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ClosetItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(body: ClosetItemCreate, user_id: CurrentUser):
    svc = _get_svc()
    return await svc.create_item(UUID(user_id), body)


@router.post(
    "/upload",
    response_model=ClosetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload garment image + auto-detect attributes via AI Vision",
)
async def upload_item(
    user_id: CurrentUser,
    file: UploadFile = File(...),
    name: str | None = None,
    category: str | None = None,
):
    content_type = file.content_type or "image/jpeg"
    if content_type not in _ALLOWED_MEDIA:
        raise BadRequestError(f"Unsupported image type: {content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > _MAX_UPLOAD_MB * 1024 * 1024:
        raise BadRequestError(f"Image exceeds {_MAX_UPLOAD_MB} MB limit")

    image_url = _persist_upload(image_bytes, content_type, file.filename)

    vision: dict = {}
    try:
        raw = await ai_client.analyze_image(image_bytes, content_type)
        vision = raw if isinstance(raw, dict) else {}
    except Exception:
        vision = {}

    item_data = ClosetItemCreate(
        name=name or str(vision.get("name") or "Clothing Item"),
        category=_normalise_category(
            category or (str(vision["category"]) if vision.get("category") else None)
        ),
        color=str(vision["color"]) if vision.get("color") else None,
        fabric=str(vision["material"]) if vision.get("material") else None,
        pattern=str(vision["pattern"]) if vision.get("pattern") else None,
        season=str(vision["season"]) if vision.get("season") else None,
        occasion=list(vision["occasion"]) if isinstance(vision.get("occasion"), list) else [],
        eco_score=float(vision["eco_score"]) if vision.get("eco_score") is not None else None,
        image_url=image_url,
        notes=str(vision["notes"]) if vision.get("notes") else None,
    )

    svc = _get_svc()
    item = await svc.create_item(UUID(user_id), item_data)
    return ClosetUploadResponse(item=item, vision_analysis=vision)


@router.post(
    "/upload/async",
    response_model=AsyncAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload garment image and queue async AI Vision analysis",
)
async def upload_item_async(
    user_id: CurrentUser,
    session: DbSession,  # Postgres session only needed for create_request
    file: UploadFile = File(...),
    name: str | None = None,
    category: str | None = None,
):
    content_type = file.content_type or "image/jpeg"
    if content_type not in _ALLOWED_MEDIA:
        raise BadRequestError(f"Unsupported image type: {content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > _MAX_UPLOAD_MB * 1024 * 1024:
        raise BadRequestError(f"Image exceeds {_MAX_UPLOAD_MB} MB limit")

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
async def update_item(item_id: UUID, body: ClosetItemUpdate, user_id: CurrentUser):
    svc = _get_svc()
    return await svc.update_item(item_id, UUID(user_id), body)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, user_id: CurrentUser):
    svc = _get_svc()
    await svc.delete_item(item_id, UUID(user_id))


# ── Wear log ──────────────────────────────────────────────────────────────────

@router.post("/{item_id}/wear", response_model=ClosetItemResponse)
async def log_wear(item_id: UUID, body: LogWearRequest, user_id: CurrentUser):
    svc = _get_svc()
    return await svc.log_wear(item_id, UUID(user_id), body.worn_date)
