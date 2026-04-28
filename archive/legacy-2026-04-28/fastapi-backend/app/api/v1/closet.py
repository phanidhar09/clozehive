"""
Closet CRUD endpoints.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, CurrentUser
from app.core.config import settings
from app.models.closet import ClosetItem
from app.schemas.closet import ClosetItemCreate, ClosetItemResponse, ClosetItemUpdate
from app.services.cache_service import cache, CacheKeys

router = APIRouter(prefix="/closet", tags=["Closet"])


@router.get("/", response_model=List[ClosetItemResponse])
async def list_items(current_user: CurrentUser, db: DB) -> List[ClosetItemResponse]:
    """List all closet items for the authenticated user."""
    # Try cache
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
    """Add a new item to the closet."""
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
