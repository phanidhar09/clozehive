"""Closet item repository for vision-service."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select

from app.models.closet import ClosetItem
from app.repositories.base import BaseRepository


class ClosetRepository(BaseRepository[ClosetItem]):
    model = ClosetItem

    async def get_owned(self, item_id: UUID, user_id: UUID) -> ClosetItem | None:
        """Return item only if it belongs to the given user."""
        result = await self.session.execute(
            select(ClosetItem).where(
                and_(ClosetItem.id == item_id, ClosetItem.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()
