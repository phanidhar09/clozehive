"""Social graph request/response schemas."""

from __future__ import annotations

from typing import Optional

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PublicUserResponse(BaseModel):
    id: UUID
    username: str
    name: str
    bio: Optional[str]
    avatar_url: Optional[str]
    follower_count: int
    following_count: int
    item_count: int
    is_following: bool

    model_config = {"from_attributes": True}


class FollowResponse(BaseModel):
    following: bool
    follower_count: int


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    is_private: bool = False


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_private: Optional[bool] = None
    avatar_url: Optional[str] = None


class GroupMemberResponse(BaseModel):
    user_id: UUID
    username: str
    name: str
    avatar_url: Optional[str]
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    owner_id: UUID
    is_private: bool
    invite_code: str
    avatar_url: Optional[str]
    member_count: int
    members: list[GroupMemberResponse]
    my_role: Optional[str]
    is_member: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class JoinGroupRequest(BaseModel):
    invite_code: str = Field(..., min_length=1)


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|member)$")
