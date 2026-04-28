"""Social graph repositories — follows, groups, group members."""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import and_, func, select

from app.models.social import Follow, Group, GroupMember
from app.models.user import User
from app.repositories.base import BaseRepository


class FollowRepository(BaseRepository[Follow]):
    model = Follow

    async def is_following(self, follower_id: UUID, following_id: UUID) -> bool:
        return await self.exists(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        )

    async def get_followers(self, user_id: UUID) -> list[User]:
        result = await self.session.execute(
            select(User)
            .join(Follow, Follow.follower_id == User.id)
            .where(Follow.following_id == user_id)
            .order_by(Follow.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_following(self, user_id: UUID) -> list[User]:
        result = await self.session.execute(
            select(User)
            .join(Follow, Follow.following_id == User.id)
            .where(Follow.follower_id == user_id)
            .order_by(Follow.created_at.desc())
        )
        return list(result.scalars().all())

    async def follower_count(self, user_id: UUID) -> int:
        return await self.count(Follow.following_id == user_id)

    async def following_count(self, user_id: UUID) -> int:
        return await self.count(Follow.follower_id == user_id)


class GroupRepository(BaseRepository[Group]):
    model = Group

    @staticmethod
    def _new_invite_code() -> str:
        return secrets.token_urlsafe(8)[:10].upper()

    async def get_by_invite_code(self, code: str) -> Group | None:
        result = await self.session.execute(
            select(Group).where(Group.invite_code == code.upper())
        )
        return result.scalar_one_or_none()

    async def get_user_groups(self, user_id: UUID) -> list[Group]:
        """Groups where the user is owner or member."""
        result = await self.session.execute(
            select(Group)
            .outerjoin(GroupMember, and_(
                GroupMember.group_id == Group.id,
                GroupMember.user_id == user_id,
            ))
            .where(
                (Group.owner_id == user_id) | (GroupMember.user_id == user_id)
            )
            .order_by(Group.created_at.desc())
        )
        return list(result.scalars().unique().all())

    async def get_public_groups(self, exclude_user_id: UUID, limit: int = 20) -> list[Group]:
        """Public groups the user has not joined."""
        joined_subq = (
            select(GroupMember.group_id)
            .where(GroupMember.user_id == exclude_user_id)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Group)
            .where(
                and_(
                    Group.is_private == False,
                    Group.owner_id != exclude_user_id,
                    Group.id.not_in(joined_subq),
                )
            )
            .order_by(Group.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class GroupMemberRepository(BaseRepository[GroupMember]):
    model = GroupMember

    async def get_membership(self, group_id: UUID, user_id: UUID) -> GroupMember | None:
        result = await self.session.execute(
            select(GroupMember).where(
                and_(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_members_with_users(self, group_id: UUID) -> list[tuple[GroupMember, User]]:
        result = await self.session.execute(
            select(GroupMember, User)
            .join(User, User.id == GroupMember.user_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.joined_at.asc())
        )
        return list(result.all())

    async def member_count(self, group_id: UUID) -> int:
        return await self.count(GroupMember.group_id == group_id)
