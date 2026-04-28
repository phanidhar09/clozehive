"""
Closet routes — /api/v1/closet/*
Full CRUD + wear logging + AI vision upload.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError
from app.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
    ClosetUploadResponse,
    LogWearRequest,
)
from app.services import ai_client
from app.services.closet_service import ClosetService

router = APIRouter(prefix="/closet", tags=["Closet"])

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/heic"}
_MAX_UPLOAD_MB = 10

_ALLOWED_CATEGORIES = frozenset(
    {"tops", "bottoms", "shoes", "outerwear", "dresses", "accessories"},
)


def _normalise_category(value: str | None) -> str:
    if not value:
        return "tops"
    key = str(value).strip().lower()
    return key if key in _ALLOWED_CATEGORIES else "tops"


def _svc(session: DbSession) -> ClosetService:
    return ClosetService(session)


# ── List / get ────────────────────────────────────────────────────────────────

@router.get("/", response_model=ClosetListResponse)
async def list_items(
    user_id: CurrentUser,
    svc: ClosetService = __import__("fastapi").Depends(_svc),
    category: str | None = Query(None),
    season: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """List all closet items for the current user. Supports filtering and pagination."""
    from uuid import UUID as _UUID
    return await svc.list_items(
        _UUID(user_id), category=category, season=season, page=page, per_page=per_page
    )


@router.get("/{item_id}", response_model=ClosetItemResponse)
async def get_item(
    item_id: UUID,
    user_id: CurrentUser,
    svc: ClosetService = __import__("fastapi").Depends(_svc),
):
    return await svc.get_item(item_id, UUID(user_id))


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ClosetItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ClosetItemCreate,
    user_id: CurrentUser,
    svc: ClosetService = __import__("fastapi").Depends(_svc),
):
    """Add a closet item manually (no image upload)."""
    return await svc.create_item(UUID(user_id), body)


@router.post(
    "/upload",
    response_model=ClosetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload garment image + auto-detect attributes via AI Vision",
)
async def upload_item(
    user_id: CurrentUser,
    session: DbSession,
    file: UploadFile = File(...),
    name: str | None = None,
    category: str | None = None,
):
    """
    Upload a clothing image. GPT-4o Vision analyses it and pre-fills
    garment attributes. You can optionally override name/category.
    """
    content_type = file.content_type or "image/jpeg"
    if content_type not in _ALLOWED_MEDIA:
        raise BadRequestError(f"Unsupported image type: {content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > _MAX_UPLOAD_MB * 1024 * 1024:
        raise BadRequestError(f"Image exceeds {_MAX_UPLOAD_MB} MB limit")

    # Call AI vision service (best-effort — falls back gracefully)
    vision: dict[str, object] = {}
    try:
        raw = await ai_client.analyze_image(image_bytes, content_type)
        vision = raw if isinstance(raw, dict) else {}
    except Exception:
        vision = {}

    item_data = ClosetItemCreate(
        name=name or str(vision.get("name") or "Clothing Item"),
        category=_normalise_category(category or (vision.get("category") if vision.get("category") else None)),
        color=str(vision["color"]) if vision.get("color") else None,
        fabric=str(vision["material"]) if vision.get("material") else None,
        pattern=str(vision["pattern"]) if vision.get("pattern") else None,
        season=str(vision["season"]) if vision.get("season") else None,
        occasion=list(vision["occasion"]) if isinstance(vision.get("occasion"), list) else [],
        eco_score=float(vision["eco_score"]) if vision.get("eco_score") is not None else None,
        notes=str(vision["notes"]) if vision.get("notes") else None,
    )

    svc = ClosetService(session)
    item = await svc.create_item(UUID(user_id), item_data)
    return ClosetUploadResponse(item=item, vision_analysis=vision)


# ── Update / delete ───────────────────────────────────────────────────────────

@router.patch("/{item_id}", response_model=ClosetItemResponse)
async def update_item(
    item_id: UUID,
    body: ClosetItemUpdate,
    user_id: CurrentUser,
    svc: ClosetService = __import__("fastapi").Depends(_svc),
):
    return await svc.update_item(item_id, UUID(user_id), body)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    user_id: CurrentUser,
    svc: ClosetService = __import__("fastapi").Depends(_svc),
):
    await svc.delete_item(item_id, UUID(user_id))


# ── Wear log ──────────────────────────────────────────────────────────────────

@router.post("/{item_id}/wear", response_model=ClosetItemResponse)
async def log_wear(
    item_id: UUID,
    body: LogWearRequest,
    user_id: CurrentUser,
    svc: ClosetService = __import__("fastapi").Depends(_svc),
):
    """Increment wear count and update last_worn date."""
    return await svc.log_wear(item_id, UUID(user_id), body.worn_date)
