"""
Follow / unfollow service — also broadcasts real-time updates via Redis.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import Follow
from app.models.user import User
from app.models.closet import ClosetItem
from app.schemas.social import FollowResponse, UserSearchItem
from app.schemas.user import UserProfileResponse, ClosetPreviewItem
from app.services.cache_service import cache, CacheKeys

logger = logging.getLogger("clozehive.social")


class SocialService:

    @staticmethod
    async def follow(db: AsyncSession, follower_id: int, target_id: int) -> FollowResponse:
        if follower_id == target_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself")

        target = await db.get(User, target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        existing = await db.scalar(
            select(Follow).where(Follow.follower_id == follower_id, Follow.following_id == target_id)
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following")

        db.add(Follow(follower_id=follower_id, following_id=target_id))
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following")

        new_count = await db.scalar(
            select(func.count()).select_from(Follow).where(Follow.following_id == target_id)
        ) or 0

        # Invalidate caches
        await cache.delete(CacheKeys.user_profile(target_id), CacheKeys.user_profile(follower_id))

        # Real-time broadcast
        await cache.publish(f"user:{target_id}", {
            "type": "follower_update",
            "follower_count": new_count,
            "actor_id": follower_id,
            "action": "follow",
        })

        return FollowResponse(following=True, follower_count=new_count)

    @staticmethod
    async def unfollow(db: AsyncSession, follower_id: int, target_id: int) -> FollowResponse:
        row = await db.scalar(
            select(Follow).where(Follow.follower_id == follower_id, Follow.following_id == target_id)
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not following this user")

        await db.delete(row)
        await db.flush()

        new_count = await db.scalar(
            select(func.count()).select_from(Follow).where(Follow.following_id == target_id)
        ) or 0

        await cache.delete(CacheKeys.user_profile(target_id), CacheKeys.user_profile(follower_id))

        await cache.publish(f"user:{target_id}", {
            "type": "follower_update",
            "follower_count": new_count,
            "actor_id": follower_id,
            "action": "unfollow",
        })

        return FollowResponse(following=False, follower_count=new_count)

    @staticmethod
    async def get_followers(db: AsyncSession, user_id: int, viewer_id: int | None = None) -> List[UserSearchItem]:
        rows = (await db.scalars(
            select(User)
            .join(Follow, Follow.follower_id == User.id)
            .where(Follow.following_id == user_id)
            .order_by(Follow.created_at.desc())
        )).all()
        return await SocialService._enrich_users(db, rows, viewer_id)

    @staticmethod
    async def get_following(db: AsyncSession, user_id: int, viewer_id: int | None = None) -> List[UserSearchItem]:
        rows = (await db.scalars(
            select(User)
            .join(Follow, Follow.following_id == User.id)
            .where(Follow.follower_id == user_id)
            .order_by(Follow.created_at.desc())
        )).all()
        return await SocialService._enrich_users(db, rows, viewer_id)

    @staticmethod
    async def _enrich_users(db: AsyncSession, users: list, viewer_id: int | None) -> List[UserSearchItem]:
        result = []
        for u in users:
            is_following = False
            if viewer_id and viewer_id != u.id:
                is_following = bool(await db.scalar(
                    select(Follow).where(
                        Follow.follower_id == viewer_id, Follow.following_id == u.id
                    )
                ))
            fc = await db.scalar(
                select(func.count()).select_from(Follow).where(Follow.following_id == u.id)
            ) or 0
            fwc = await db.scalar(
                select(func.count()).select_from(Follow).where(Follow.follower_id == u.id)
            ) or 0
            ic = await db.scalar(
                select(func.count()).select_from(ClosetItem).where(ClosetItem.owner_id == u.id)
            ) or 0
            result.append(UserSearchItem(
                id=u.id, name=u.name, username=u.username,
                avatar_url=u.avatar_url, bio=u.bio,
                follower_count=fc, following_count=fwc,
                is_following=is_following, item_count=ic,
            ))
        return result
