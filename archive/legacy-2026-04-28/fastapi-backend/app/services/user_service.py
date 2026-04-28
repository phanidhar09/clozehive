"""
User profile service.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.social import Follow
from app.models.closet import ClosetItem
from app.schemas.user import MeResponse, UpdateMeRequest, UserProfileResponse, ClosetPreviewItem
from app.services.cache_service import cache, CacheKeys

logger = logging.getLogger("clozehive.users")


class UserService:

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        return await db.get(User, user_id)

    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
        return await db.scalar(select(User).where(User.username == username.lower()))

    # ── Profile ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get_profile(
        db: AsyncSession,
        target_user_id: int,
        viewer_id: Optional[int] = None,
    ) -> UserProfileResponse:
        # Try cache first
        cache_key = CacheKeys.user_profile(target_user_id)
        cached = await cache.get(cache_key)

        if cached and viewer_id is None:
            return UserProfileResponse(**cached)

        user = await db.get(User, target_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        follower_count = await db.scalar(
            select(func.count()).select_from(Follow).where(Follow.following_id == target_user_id)
        ) or 0

        following_count = await db.scalar(
            select(func.count()).select_from(Follow).where(Follow.follower_id == target_user_id)
        ) or 0

        item_count = await db.scalar(
            select(func.count()).select_from(ClosetItem).where(ClosetItem.owner_id == target_user_id)
        ) or 0

        is_following = False
        if viewer_id and viewer_id != target_user_id:
            is_following = bool(await db.scalar(
                select(Follow).where(
                    Follow.follower_id == viewer_id,
                    Follow.following_id == target_user_id,
                )
            ))

        # Closet preview (latest 6 items)
        preview_rows = (await db.scalars(
            select(ClosetItem)
            .where(ClosetItem.owner_id == target_user_id)
            .order_by(ClosetItem.created_at.desc())
            .limit(6)
        )).all()

        preview = [
            ClosetPreviewItem(
                id=item.id,
                name=item.name,
                category=item.category,
                image_url=item.image_url,
            )
            for item in preview_rows
        ]

        profile = UserProfileResponse(
            id=user.id,
            name=user.name,
            username=user.username,
            bio=user.bio,
            avatar_url=user.avatar_url,
            follower_count=follower_count,
            following_count=following_count,
            item_count=item_count,
            is_following=is_following,
            created_at=user.created_at,
            closet_preview=preview,
        )

        # Cache profile without viewer-specific data
        if viewer_id is None:
            await cache.set(cache_key, profile.model_dump(), ttl=settings.CACHE_TTL_PROFILE)

        return profile

    # ── Me ────────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_me(db: AsyncSession, user_id: int) -> MeResponse:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        follower_count = await db.scalar(
            select(func.count()).select_from(Follow).where(Follow.following_id == user_id)
        ) or 0
        following_count = await db.scalar(
            select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
        ) or 0
        item_count = await db.scalar(
            select(func.count()).select_from(ClosetItem).where(ClosetItem.owner_id == user_id)
        ) or 0

        return MeResponse(
            id=user.id,
            name=user.name,
            username=user.username,
            email=user.email,
            bio=user.bio,
            avatar_url=user.avatar_url,
            follower_count=follower_count,
            following_count=following_count,
            item_count=item_count,
            created_at=user.created_at,
        )

    @staticmethod
    async def update_me(db: AsyncSession, user_id: int, data: UpdateMeRequest) -> MeResponse:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if data.name is not None:
            user.name = data.name
        if data.bio is not None:
            user.bio = data.bio
        if data.avatar_url is not None:
            user.avatar_url = data.avatar_url

        await db.flush()

        # Invalidate caches
        await cache.delete(
            CacheKeys.user_profile(user_id),
            CacheKeys.user_by_username(user.username),
        )

        return await UserService.get_me(db, user_id)

    # ── Search ────────────────────────────────────────────────────────────────

    @staticmethod
    async def search_users(
        db: AsyncSession,
        query: str,
        viewer_id: Optional[int] = None,
        limit: int = 20,
    ):
        from app.schemas.social import UserSearchItem  # avoid circular at module level

        q = f"%{query.lower()}%"
        rows = (await db.scalars(
            select(User)
            .where(
                User.is_active == True,  # noqa: E712
                (func.lower(User.name).like(q) | func.lower(User.username).like(q)),
            )
            .limit(limit)
        )).all()

        result = []
        for u in rows:
            is_following = False
            if viewer_id and viewer_id != u.id:
                is_following = bool(await db.scalar(
                    select(Follow).where(
                        Follow.follower_id == viewer_id,
                        Follow.following_id == u.id,
                    )
                ))
            follower_count = await db.scalar(
                select(func.count()).select_from(Follow).where(Follow.following_id == u.id)
            ) or 0
            following_count = await db.scalar(
                select(func.count()).select_from(Follow).where(Follow.follower_id == u.id)
            ) or 0
            item_count = await db.scalar(
                select(func.count()).select_from(ClosetItem).where(ClosetItem.owner_id == u.id)
            ) or 0
            result.append(UserSearchItem(
                id=u.id,
                name=u.name,
                username=u.username,
                avatar_url=u.avatar_url,
                bio=u.bio,
                follower_count=follower_count,
                following_count=following_count,
                is_following=is_following,
                item_count=item_count,
            ))
        return result
