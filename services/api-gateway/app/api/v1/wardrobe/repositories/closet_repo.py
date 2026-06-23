"""Closet item repository."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, select

from app.models.closet import ClosetItem, WearEvent
from app.repositories.base import BaseRepository


class ClosetRepository(BaseRepository[ClosetItem]):
    model = ClosetItem

    async def get_by_user(
        self,
        user_id: UUID,
        *,
        section: str | None = None,
        category: str | None = None,
        season: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ClosetItem]:
        conditions = [ClosetItem.user_id == user_id]
        if not include_archived:
            conditions.append(ClosetItem.is_archived == False)  # noqa: E712
        if section:
            conditions.append(ClosetItem.section == section)
        if category:
            conditions.append(ClosetItem.category == category)
        if season:
            # season is now ARRAY(String); use @> (contains) to match items that
            # include the requested season value anywhere in their seasons list.
            conditions.append(ClosetItem.season.contains([season]))

        result = await self.session.execute(
            select(ClosetItem)
            .where(and_(*conditions))
            .order_by(ClosetItem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        """Count non-archived items owned by a user."""
        return await self.count(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
        )

    async def add_wear_event(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        worn_on: date,
        source: str = "manual",
        outfit_id: UUID | None = None,
    ) -> None:
        """Append a row to the wear history. Caller's transaction commits it."""
        self.session.add(
            WearEvent(
                user_id=user_id,
                item_id=item_id,
                worn_on=worn_on,
                source=source,
                outfit_id=outfit_id,
            )
        )

    async def get_owned(self, item_id: UUID, user_id: UUID) -> ClosetItem | None:
        """Return item only if it belongs to the given user."""
        result = await self.session.execute(
            select(ClosetItem).where(and_(ClosetItem.id == item_id, ClosetItem.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def get_many_by_user(
        self,
        user_id: UUID,
        item_ids: list[UUID],
    ) -> dict[UUID, ClosetItem]:
        """Bulk-fetch items belonging to a user, keyed by id."""
        if not item_ids:
            return {}
        result = await self.session.execute(
            select(ClosetItem).where(
                and_(
                    ClosetItem.user_id == user_id,
                    ClosetItem.id.in_(item_ids),
                )
            )
        )
        return {item.id: item for item in result.scalars().all()}
