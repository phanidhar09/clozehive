"""
Group schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class GroupMemberResponse(BaseModel):
    id: int
    name: str
    username: str
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    creator_id: Optional[int] = None
    invite_code: str
    is_public: bool
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    members: List[GroupMemberResponse] = []
    my_role: Optional[str] = None
    is_member: bool = False

    model_config = {"from_attributes": True}


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    is_public: bool = True


class JoinGroupRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=16)


class InviteToGroupRequest(BaseModel):
    user_id: int


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern=r"^(admin|member)$")
