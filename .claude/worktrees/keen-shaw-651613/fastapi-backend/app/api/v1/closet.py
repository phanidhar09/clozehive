"""
Closet CRUD endpoints + image upload with AI vision analysis.
"""
from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.models.closet import ClosetItem
from app.schemas.closet import ClosetItemCreate, ClosetItemResponse, ClosetItemUpdate
from app.services.cache_service import CacheKeys, cache

router = APIRouter(prefix="/closet", tags=["Closet"])

# Local directory for storing processed (bg-removed) images
UPLOADS_DIR = Path(__file__).resolve().parents[4] / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _garment_to_category(garment_type: str) -> str:
    """Map AI garment_type to frontend category value."""
    mapping = {
        "shirt": "tops", "t-shirt": "tops", "blouse": "tops", "top": "tops",
        "sweater": "tops", "hoodie": "tops", "tank": "tops", "polo": "tops",
        "pants": "bottoms", "jeans": "bottoms", "trousers": "bottoms",
        "shorts": "bottoms", "skirt": "bottoms", "leggings": "bottoms",
        "dress": "dresses", "gown": "dresses", "romper": "dresses",
        "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear",
        "windbreaker": "outerwear", "parka": "outerwear",
        "shoes": "shoes", "sneakers": "shoes", "boots": "shoes",
        "sandals": "shoes", "heels": "shoes", "loafers": "shoes",
        "bag": "accessories", "belt": "accessories", "hat": "accessories",
        "scarf": "accessories", "watch": "accessories", "jewelry": "accessories",
    }
    return mapping.get(garment_type.lower(), "tops")


def _save_processed_image(b64_data: str, media_type: str) -> Optional[str]:
    """
    Decode base64 image and save to uploads directory.
    Returns a relative URL like /uploads/<filename>.png, or None on error.
    """
    if not b64_data:
        return None
    try:
        ext = "png" if "png" in media_type else "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        file_path = UPLOADS_DIR / filename
        file_path.write_bytes(base64.b64decode(b64_data))
        return f"/uploads/{filename}"
    except Exception as e:
        print(f"[Upload] Failed to save processed image: {e}")
        return None


async def _call_vision_api(image_bytes: bytes, content_type: str) -> Dict[str, Any]:
    """Call the AI service /vision/analyze endpoint."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.AI_SERVICE_URL}/vision/analyze",
                files={"image": ("image", image_bytes, content_type)},
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"[Upload] Vision API call failed: {e}")
        return {}


async def _call_outfit_api(image_bytes: bytes, content_type: str) -> Dict[str, Any]:
    """Call the AI service /vision/analyze-outfit endpoint."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.AI_SERVICE_URL}/vision/analyze-outfit",
                files={"image": ("image", image_bytes, content_type)},
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"[Upload] Outfit API call failed: {e}")
        return {}


# ── Upload endpoint ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_item(
    current_user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    is_outfit: Optional[bool] = Form(False),
) -> Dict[str, Any]:
    """
    Upload a clothing image.

    - Single item photo  → vision analysis + background removal → creates DB item
    - Outfit/full-body photo (is_outfit=true) → detects all worn items + bg removal
      Returns detected items for the frontend to confirm before creating DB entries.

    Response always includes `processed_image_base64` for instant display.
    """
    allowed = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    content_type = file.content_type or "image/jpeg"
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    # ── Outfit photo path ──────────────────────────────────────────────────────
    if is_outfit:
        outfit_data = await _call_outfit_api(image_bytes, content_type)
        processed_url = _save_processed_image(
            outfit_data.get("processed_image_base64", ""),
            outfit_data.get("processed_image_media_type", "image/png"),
        )
        return {
            "mode": "outfit",
            "is_outfit_photo": True,
            "detected_items": outfit_data.get("items", []),
            "processed_image_url": processed_url,
            "processed_image_base64": outfit_data.get("processed_image_base64", ""),
            "processed_image_media_type": outfit_data.get("processed_image_media_type", "image/png"),
        }

    # ── Single item path ───────────────────────────────────────────────────────
    vision = await _call_vision_api(image_bytes, content_type)

    # Save the background-removed image
    processed_url = _save_processed_image(
        vision.get("processed_image_base64", ""),
        vision.get("processed_image_media_type", "image/png"),
    )

    # Derive item attributes from vision analysis
    garment_type = vision.get("garment_type", "")
    item_category = category or _garment_to_category(garment_type)
    item_name = (
        name
        or (f"{vision.get('color_primary', '')} {garment_type}".strip().title() if garment_type else "")
        or "New Item"
    )
    color = vision.get("color_primary") or None
    tags: List[str] = []
    if vision.get("fabric"):
        tags.append(vision["fabric"])
    if vision.get("pattern") and vision["pattern"] != "solid":
        tags.append(vision["pattern"])
    for occ in (vision.get("occasion") or []):
        tags.append(occ)

    # Create the DB item
    db_item = ClosetItem(
        name=item_name,
        category=item_category,
        color=color,
        image_url=processed_url,
        tags=tags,
        owner_id=current_user.id,
    )
    db.add(db_item)
    await db.flush()
    await cache.delete(CacheKeys.closet(current_user.id))

    item_response = ClosetItemResponse.model_validate(db_item)

    return {
        "mode": "single",
        "item": item_response.model_dump(),
        "vision_analysis": {k: v for k, v in vision.items() if k not in ("processed_image_base64", "processed_image_media_type")},
        "processed_image_url": processed_url,
        "processed_image_base64": vision.get("processed_image_base64", ""),
        "processed_image_media_type": vision.get("processed_image_media_type", "image/png"),
    }


@router.post("/upload/confirm-outfit-items", status_code=201)
async def confirm_outfit_items(
    current_user: CurrentUser,
    db: DB,
    items: List[Dict[str, Any]],
    processed_image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create DB entries for confirmed items from an outfit photo.
    `items` is the list from the outfit detection response (after user confirmation).
    """
    created = []
    for item_data in items:
        garment_type = item_data.get("garment_type", "")
        suggested_name = item_data.get("suggested_name", "")
        category = item_data.get("category") or _garment_to_category(garment_type)
        item_name = suggested_name or f"{item_data.get('color_primary', '')} {garment_type}".strip().title() or "New Item"

        tags: List[str] = []
        if item_data.get("fabric"):
            tags.append(item_data["fabric"])
        for occ in (item_data.get("occasion") or []):
            tags.append(occ)

        db_item = ClosetItem(
            name=item_name,
            category=category,
            color=item_data.get("color_primary"),
            image_url=processed_image_url,
            tags=tags,
            owner_id=current_user.id,
        )
        db.add(db_item)
        await db.flush()
        created.append(ClosetItemResponse.model_validate(db_item).model_dump())

    await cache.delete(CacheKeys.closet(current_user.id))
    return {"created": created, "count": len(created)}


# ── Standard CRUD ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ClosetItemResponse])
async def list_items(current_user: CurrentUser, db: DB) -> List[ClosetItemResponse]:
    cache_key = CacheKeys.closet(current_user.id)
    cached = await cache.get(cache_key)
    if cached:
        return [ClosetItemResponse(**item) for item in cached]

    items = (await db.scalars(
        select(ClosetItem)
        .where(ClosetItem.owner_id == current_user.id)
        .order_by(ClosetItem.created_at.desc())
    )).all()

    result = [ClosetItemResponse.model_validate(item) for item in items]
    await cache.set(cache_key, [r.model_dump() for r in result], ttl=settings.CACHE_TTL_CLOSET)
    return result


@router.post("/", response_model=ClosetItemResponse, status_code=201)
async def add_item(body: ClosetItemCreate, current_user: CurrentUser, db: DB) -> ClosetItemResponse:
    item = ClosetItem(**body.model_dump(), owner_id=current_user.id)
    db.add(item)
    await db.flush()
    await cache.delete(CacheKeys.closet(current_user.id))
    return ClosetItemResponse.model_validate(item)


@router.get("/{item_id}", response_model=ClosetItemResponse)
async def get_item(item_id: int, current_user: CurrentUser, db: DB) -> ClosetItemResponse:
    item = await db.get(ClosetItem, item_id)
    if item is None or item.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return ClosetItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=ClosetItemResponse)
async def update_item(
    item_id: int, body: ClosetItemUpdate, current_user: CurrentUser, db: DB
) -> ClosetItemResponse:
    item = await db.get(ClosetItem, item_id)
    if item is None or item.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    await db.flush()
    await cache.delete(CacheKeys.closet(current_user.id))
    return ClosetItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int, current_user: CurrentUser, db: DB) -> None:
    item = await db.get(ClosetItem, item_id)
    if item is None or item.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    await db.delete(item)
    await cache.delete(CacheKeys.closet(current_user.id))
