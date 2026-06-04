"""
Closet service — business logic on top of the repository.
Handles cache invalidation, access control, wear-log, and file upload.
"""

from __future__ import annotations

import re
from typing import Optional

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.repositories.closet_repo import ClosetRepository
from app.repositories.style_profile_repo import UserStyleProfileRepository
from app.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
)
from app.services import cache_service
from app.services.upload_service import signed_url_for_stored

logger = get_logger("closet_service")
settings = get_settings()

_CACHE_TTL = settings.cache_ttl_closet

_MASCULINE_HINTS = frozenset({
    "mens",
    "men",
    "male",
    "boy",
    "boys",
    "gent",
    "gentleman",
    "brogue",
})
_FEMININE_HINTS = frozenset({
    "womens",
    "women",
    "female",
    "girl",
    "girls",
    "lady",
    "ladies",
    "dress",
    "skirt",
    "blouse",
    "bra",
    "heels",
    "stiletto",
    "saree",
    "lehenga",
    "kurti",
})
_WORD_RE = re.compile(r"[a-z]+")


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


def _profile_gender_value(raw: str | None) -> str | None:
    if not raw:
        return None
    t = str(raw).strip().lower()
    if t in {"male", "man", "men"}:
        return "male"
    if t in {"female", "woman", "women"}:
        return "female"
    if t == "custom":
        return None
    return None


def _infer_item_gender(data: ClosetItemCreate) -> str | None:
    text_parts = [
        data.name or "",
        data.category or "",
        data.notes or "",
        " ".join(data.tags or []),
        data.brand or "",
    ]
    text = " ".join(text_parts).lower()
    words = set(_WORD_RE.findall(text))

    male_hits = words.intersection(_MASCULINE_HINTS)
    female_hits = words.intersection(_FEMININE_HINTS)

    # Dresses are a high-signal feminine-coded category in current taxonomy.
    if data.category == "dresses":
        female_hits = set(female_hits) | {"dresses"}

    if male_hits and female_hits:
        return None
    if male_hits:
        return "male"
    if female_hits:
        return "female"
    return None


class ClosetService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ClosetRepository(session)

    async def list_items(
        self,
        user_id: UUID,
        *,
        section: Optional[str] = None,
        category: Optional[str] = None,
        season: Optional[str] = None,
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
        profile_row = await UserStyleProfileRepository(self.repo.session).get_by_user_id(user_id)
        profile_gender = _profile_gender_value(getattr(profile_row, "gender", None))
        if profile_gender is None and profile_row and getattr(profile_row, "custom_gender", None):
            profile_gender = _profile_gender_value(profile_row.custom_gender)

        item_gender = _infer_item_gender(data)
        if (
            profile_gender
            and item_gender
            and profile_gender != item_gender
            and not data.confirm_gender_mismatch
        ):
            raise ForbiddenError(
                "This item appears to mismatch your saved gender style profile.",
                detail=(
                    "This item looks "
                    f"{item_gender}-coded while your profile is {profile_gender}. "
                    "If you still want to add it, please confirm by resubmitting with "
                    "confirm_gender_mismatch=true."
                ),
            )

        payload = data.model_dump(exclude={"confirm_gender_mismatch"})
        item = await self.repo.create(user_id=user_id, **payload)
        await cache_service.invalidate_closet_list_cache(str(user_id))
        logger.info("closet_item_created", user_id=str(user_id), item_id=str(item.id))
        return _to_response(item)

    async def update_item(
        self, item_id: UUID, user_id: UUID, data: ClosetItemUpdate
    ) -> ClosetItemResponse:
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
            u for u in (
                item.original_image_url,
                item.processed_image_url,
                item.image_url,
            )
            if u
        ]
        await self.repo.delete(item)
        await cache_service.invalidate_closet_list_cache(str(user_id))
        logger.info("closet_item_deleted", user_id=str(user_id), item_id=str(item_id))
        return image_urls

    async def log_wear(self, item_id: UUID, user_id: UUID, worn_date: date | None = None) -> ClosetItemResponse:
        item = await self.repo.get_owned(item_id, user_id)
        if not item:
            raise NotFoundError(f"Item {item_id} not found")
        updated = await self.repo.update(
            item,
            wear_count=item.wear_count + 1,
            last_worn=worn_date or date.today(),
        )
        await cache_service.invalidate_closet_list_cache(str(user_id))
        return _to_response(updated)
