"""Closet item repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_, select

from app.models.closet import ClosetItem
from app.repositories.base import BaseRepository


class ClosetRepository(BaseRepository[ClosetItem]):
    model = ClosetItem

    async def get_by_user(
        self,
        user_id: UUID,
        *,
        category: str | None = None,
        season: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClosetItem]:
        conditions = [ClosetItem.user_id == user_id]
        if not include_archived:
            conditions.append(ClosetItem.is_archived == False)
        if category:
            conditions.append(ClosetItem.category == category)
        if season:
            conditions.append(ClosetItem.season == season)

        result = await self.session.execute(
            select(ClosetItem)
            .where(and_(*conditions))
            .order_by(ClosetItem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        return await self.count(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,
        )

    async def get_owned(self, item_id: UUID, user_id: UUID) -> ClosetItem | None:
        """Get item only if it belongs to the given user."""
        result = await self.session.execute(
            select(ClosetItem).where(
                and_(ClosetItem.id == item_id, ClosetItem.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()
