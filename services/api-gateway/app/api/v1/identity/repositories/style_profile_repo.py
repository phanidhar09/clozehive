"""Repository for user_style_profiles."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.user_style_profile import UserStyleProfile
from app.repositories.base import BaseRepository


class UserStyleProfileRepository(BaseRepository[UserStyleProfile]):
    model = UserStyleProfile

    async def get_by_user_id(self, user_id: UUID) -> UserStyleProfile | None:
        result = await self.session.execute(select(UserStyleProfile).where(UserStyleProfile.user_id == user_id))
        return result.scalar_one_or_none()
