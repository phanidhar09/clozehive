"""
Closet service — business logic on top of the repository.
Handles cache invalidation, access control, wear-log, and file upload.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.wardrobe.repositories.closet_repo import ClosetRepository
from app.api.v1.wardrobe.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
)
from app.core import cache_service
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.upload_service import signed_url_for_stored

logger = get_logger("closet_service")
settings = get_settings()

_CACHE_TTL = settings.cache_ttl_closet


def _to_response(item) -> ClosetItemResponse:
    resp = ClosetItemResponse.model_validate(item)
    # On a private bucket, swap stored image URLs for short-lived signed URLs so
    # only the app (via the owner's authenticated request) can serve them.
    # No-op when GCS_SIGNED_URLS is off — returns the stored value unchanged.
    if settings.gcs_signed_urls:
        resp.image_url = signed_url_for_stored(resp.image_url)
        resp.original_image_url = signed_url_for_stored(resp.original_image_url)
        resp.processed_image_url = signed_url_for_stored(resp.processed_image_url)
    return resp


class ClosetService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ClosetRepository(session)

    async def list_items(
        self,
        user_id: UUID,
        *,
        section: str | None = None,
        category: str | None = None,
        season: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> ClosetListResponse:
        cache_key = cache_service.build_closet_cache_key(
            str(user_id),
            {"category": category, "page": page, "per_page": per_page, "season": season, "section": section},
        )
        cached = await cache_service.get(cache_key)
        if cached:
            return ClosetListResponse(**cached)

        offset = (page - 1) * per_page
        items = await self.repo.get_by_user(
            user_id, section=section, category=category, season=season, limit=per_page, offset=offset
        )
        total = await self.repo.count_by_user(user_id)
        response = ClosetListResponse(
            items=[_to_response(i) for i in items],
            total=total,
            page=page,
            per_page=per_page,
        )

        await cache_service.set(cache_key, response.model_dump(mode="json"), _CACHE_TTL)
        return response

    async def get_item(self, item_id: UUID, user_id: UUID) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        return _to_response(item)

    async def create_item(self, user_id: UUID, data: ClosetItemCreate) -> ClosetItemResponse:
        payload = data.model_dump()
        # condition is NOT NULL with a server_default; an omitted value comes
        # through as None, which would violate the constraint. Drop it so the
        # DB default ('good') applies. (availability is kept out of the create
        # schema entirely for the same reason.)
        if payload.get("condition") is None:
            payload.pop("condition", None)
        item = await self.repo.create(user_id=user_id, **payload)
        await cache_service.invalidate_closet_list_cache(str(user_id))
        logger.info("closet_item_created", user_id=str(user_id), item_id=str(item.id))
        return _to_response(item)

    async def update_item(self, item_id: UUID, user_id: UUID, data: ClosetItemUpdate) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")

        updated = await self.repo.update(item, **data.model_dump(exclude_none=True))
        await cache_service.invalidate_closet_list_cache(str(user_id))
        return _to_response(updated)

    async def delete_item(self, item_id: UUID, user_id: UUID) -> list[str]:
        """Delete a closet item and return the image URLs that should be cleaned up.

        The caller is responsible for firing a background task to delete the
        actual image blobs — returned URLs may be GCS or local /uploads/ paths.
        """
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        # Collect image URLs before the row is gone
        image_urls = [
            u
            for u in (
                item.original_image_url,
                item.processed_image_url,
                item.image_url,
            )
            if u
        ]
        await self.repo.delete(item)
        # Cache invalidation happens in the route AFTER session.commit().
        # Busting Redis here (pre-commit) races with concurrent GETs that can
        # rebuild the list cache from the still-visible row and bring "deleted"
        # items back on refresh.
        logger.info("closet_item_deleted", user_id=str(user_id), item_id=str(item_id))
        return image_urls

    async def log_wear(self, item_id: UUID, user_id: UUID, worn_date: date | None = None) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        worn_on = worn_date or date.today()
        # Append to the wear history (source of truth for time-series analytics)
        # in addition to bumping the fast rollup columns on the item itself.
        await self.repo.add_wear_event(user_id=user_id, item_id=item_id, worn_on=worn_on, source="manual")
        updated = await self.repo.update(
            item,
            wear_count=item.wear_count + 1,
            last_worn=worn_on,
        )
        await cache_service.invalidate_closet_list_cache(str(user_id))
        return _to_response(updated)
