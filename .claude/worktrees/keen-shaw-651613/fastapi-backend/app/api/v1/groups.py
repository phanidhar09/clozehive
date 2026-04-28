"""
Groups endpoints.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.schemas.common import MessageResponse
from app.schemas.group import (
    ChangeRoleRequest,
    CreateGroupRequest,
    GroupResponse,
    InviteToGroupRequest,
    JoinGroupRequest,
)
from app.services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.get("/", response_model=List[GroupResponse])
async def list_my_groups(current_user: CurrentUser, db: DB) -> List[GroupResponse]:
    """List all groups the authenticated user belongs to."""
    return await GroupService.list_mine(db, current_user.id)


@router.get("/discover", response_model=List[GroupResponse])
async def discover_groups(current_user: CurrentUser, db: DB) -> List[GroupResponse]:
    """Discover public groups the user hasn't joined yet."""
    return await GroupService.discover(db, current_user.id)


@router.post("/", response_model=GroupResponse, status_code=201)
async def create_group(body: CreateGroupRequest, current_user: CurrentUser, db: DB) -> GroupResponse:
    """Create a new group. Creator becomes admin automatically."""
    return await GroupService.create(db, current_user.id, body)


@router.post("/join", response_model=GroupResponse)
async def join_group(body: JoinGroupRequest, current_user: CurrentUser, db: DB) -> GroupResponse:
    """Join a group via its invite code."""
    return await GroupService.join(db, current_user.id, body.invite_code)


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(group_id: int, current_user: CurrentUser, db: DB) -> GroupResponse:
    """Get group details (members, invite code, etc.)."""
    return await GroupService.get(db, group_id, current_user.id)


@router.post("/{group_id}/invite", response_model=GroupResponse)
async def invite_to_group(
    group_id: int,
    body: InviteToGroupRequest,
    current_user: CurrentUser,
    db: DB,
) -> GroupResponse:
    """Admin: Invite a user to the group by user_id."""
    return await GroupService.invite(db, group_id, current_user.id, body.user_id)


@router.delete("/{group_id}/members/{user_id}", response_model=GroupResponse)
async def remove_member(
    group_id: int,
    user_id: int,
    current_user: CurrentUser,
    db: DB,
) -> GroupResponse:
    """Admin: Remove a member from the group."""
    return await GroupService.remove_member(db, group_id, current_user.id, user_id)


@router.patch("/{group_id}/members/{user_id}/role", response_model=GroupResponse)
async def change_member_role(
    group_id: int,
    user_id: int,
    body: ChangeRoleRequest,
    current_user: CurrentUser,
    db: DB,
) -> GroupResponse:
    """Admin: Promote or demote a member."""
    return await GroupService.change_role(db, group_id, current_user.id, user_id, body.role)


@router.delete("/{group_id}/leave", response_model=MessageResponse)
async def leave_group(group_id: int, current_user: CurrentUser, db: DB) -> MessageResponse:
    """Leave a group."""
    await GroupService.leave(db, group_id, current_user.id)
    return MessageResponse(message="Left the group successfully")


@router.delete("/{group_id}", response_model=MessageResponse)
async def delete_group(group_id: int, current_user: CurrentUser, db: DB) -> MessageResponse:
    """Admin: Delete the group entirely."""
    await GroupService.delete_group(db, group_id, current_user.id)
    return MessageResponse(message="Group deleted successfully")
