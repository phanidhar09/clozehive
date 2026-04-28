"""
Closet service — business logic on top of the repository.
Handles cache invalidation, access control, wear-log, and file upload.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.repositories.closet_repo import ClosetRepository
from app.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
)
from app.services import cache_service

logger = get_logger("closet_service")
settings = get_settings()

_CACHE_TTL = settings.cache_ttl_closet


def _to_response(item) -> ClosetItemResponse:
    return ClosetItemResponse.model_validate(item)


class ClosetService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ClosetRepository(session)

    async def list_items(
        self,
        user_id: UUID,
        *,
        category: str | None = None,
        season: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> ClosetListResponse:
        cache_key = cache_service.closet_key(str(user_id))
        if not category and not season:
            cached = await cache_service.get(cache_key)
            if cached:
                return ClosetListResponse(**cached)

        offset = (page - 1) * per_page
        items = await self.repo.get_by_user(
            user_id, category=category, season=season, limit=per_page, offset=offset
        )
        total = await self.repo.count_by_user(user_id)
        response = ClosetListResponse(
            items=[_to_response(i) for i in items],
            total=total,
            page=page,
            per_page=per_page,
        )

        if not category and not season:
            await cache_service.set(cache_key, response.model_dump(mode="json"), _CACHE_TTL)

        return response

    async def get_item(self, item_id: UUID, user_id: UUID) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        return _to_response(item)

    async def create_item(self, user_id: UUID, data: ClosetItemCreate) -> ClosetItemResponse:
        item = await self.repo.create(user_id=user_id, **data.model_dump())
        await cache_service.delete(cache_service.closet_key(str(user_id)))
        logger.info("closet_item_created", user_id=str(user_id), item_id=str(item.id))
        return _to_response(item)

    async def update_item(
        self, item_id: UUID, user_id: UUID, data: ClosetItemUpdate
    ) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")

        updated = await self.repo.update(item, **data.model_dump(exclude_none=True))
        await cache_service.delete(cache_service.closet_key(str(user_id)))
        return _to_response(updated)

    async def delete_item(self, item_id: UUID, user_id: UUID) -> None:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        await self.repo.delete(item)
        await cache_service.delete(cache_service.closet_key(str(user_id)))
        logger.info("closet_item_deleted", user_id=str(user_id), item_id=str(item_id))

    async def log_wear(self, item_id: UUID, user_id: UUID, worn_date: date | None = None) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        updated = await self.repo.update(
            item,
            wear_count=item.wear_count + 1,
            last_worn=worn_date or date.today(),
        )
        await cache_service.delete(cache_service.closet_key(str(user_id)))
        return _to_response(updated)
