"""
Social (follow/unfollow) schemas.
"""
from __future__ import annotations

from pydantic import BaseModel


class FollowResponse(BaseModel):
    following: bool
    follower_count: int


class UserSearchItem(BaseModel):
    id: int
    name: str
    username: str
    avatar_url: str | None = None
    bio: str | None = None
    follower_count: int = 0
    following_count: int = 0
    is_following: bool = False
    item_count: int = 0

    model_config = {"from_attributes": True}
