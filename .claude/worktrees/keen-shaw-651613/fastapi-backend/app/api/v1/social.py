"""
Social graph endpoints: follow / unfollow / followers / following.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from app.core.deps import DB, CurrentUser, CurrentUserID
from app.schemas.social import FollowResponse, UserSearchItem
from app.services.social_service import SocialService

router = APIRouter(prefix="/social", tags=["Social"])


@router.post("/follow/{user_id}", response_model=FollowResponse)
async def follow_user(
    user_id: int,
    current_user: CurrentUser,
    db: DB,
) -> FollowResponse:
    """Follow a user."""
    return await SocialService.follow(db, follower_id=current_user.id, target_id=user_id)


@router.delete("/follow/{user_id}", response_model=FollowResponse)
async def unfollow_user(
    user_id: int,
    current_user: CurrentUser,
    db: DB,
) -> FollowResponse:
    """Unfollow a user."""
    return await SocialService.unfollow(db, follower_id=current_user.id, target_id=user_id)


@router.get("/followers/{user_id}", response_model=List[UserSearchItem])
async def get_followers(
    user_id: int,
    db: DB,
    current_user_id: CurrentUserID = 0,
) -> List[UserSearchItem]:
    """Get the followers list for a user."""
    return await SocialService.get_followers(db, user_id=user_id, viewer_id=current_user_id)


@router.get("/following/{user_id}", response_model=List[UserSearchItem])
async def get_following(
    user_id: int,
    db: DB,
    current_user_id: CurrentUserID = 0,
) -> List[UserSearchItem]:
    """Get the list of users someone is following."""
    return await SocialService.get_following(db, user_id=user_id, viewer_id=current_user_id)
