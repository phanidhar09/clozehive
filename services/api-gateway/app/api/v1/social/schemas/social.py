"""Social graph request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PublicUserResponse(BaseModel):
    id: UUID
    username: str
    name: str
    bio: str | None
    avatar_url: str | None
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
    description: str | None = Field(None, max_length=1000)
    is_private: bool = False


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_private: bool | None = None
    avatar_url: str | None = None


class GroupMemberResponse(BaseModel):
    user_id: UUID
    username: str
    name: str
    avatar_url: str | None
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    owner_id: UUID
    is_private: bool
    invite_code: str
    avatar_url: str | None
    member_count: int
    members: list[GroupMemberResponse]
    my_role: str | None
    is_member: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class JoinGroupRequest(BaseModel):
    invite_code: str = Field(..., min_length=1)


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|member)$")
