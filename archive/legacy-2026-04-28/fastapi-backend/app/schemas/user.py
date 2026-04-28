"""
User profile schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class UserPublicResponse(BaseModel):
    """Minimal public-facing user info."""
    id: int
    name: str
    username: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    follower_count: int = 0
    following_count: int = 0
    item_count: int = 0
    is_following: bool = False

    model_config = {"from_attributes": True}


class ClosetPreviewItem(BaseModel):
    id: int
    name: str
    category: str
    image_url: Optional[str] = None

    model_config = {"from_attributes": True}


class UserProfileResponse(UserPublicResponse):
    """Full profile — includes closet preview."""
    created_at: datetime
    closet_preview: List[ClosetPreviewItem] = []


class UpdateMeRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = Field(None, max_length=512)


class MeResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    follower_count: int = 0
    following_count: int = 0
    item_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
