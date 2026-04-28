"""
Group management service.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group import Group, GroupMember, GroupRole
from app.models.user import User
from app.schemas.group import (
    GroupResponse,
    GroupMemberResponse,
    CreateGroupRequest,
)
from app.services.cache_service import cache

logger = logging.getLogger("clozehive.groups")


def _require_admin(membership: Optional[GroupMember]) -> None:
    if membership is None or membership.role != GroupRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


async def _get_membership(db: AsyncSession, group_id: int, user_id: int) -> Optional[GroupMember]:
    return await db.scalar(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )


async def _build_response(db: AsyncSession, group: Group, viewer_id: int) -> GroupResponse:
    member_count = await db.scalar(
        select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group.id)
    ) or 0

    member_rows = (await db.scalars(
        select(GroupMember)
        .where(GroupMember.group_id == group.id)
        .order_by(GroupMember.joined_at)
        .limit(20)
    )).all()

    members: List[GroupMemberResponse] = []
    for m in member_rows:
        u = await db.get(User, m.user_id)
        if u:
            members.append(GroupMemberResponse(
                id=u.id,
                name=u.name,
                username=u.username,
                avatar_url=u.avatar_url,
                role=m.role.value,
                joined_at=m.joined_at,
            ))

    my_membership = await _get_membership(db, group.id, viewer_id)

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        creator_id=group.creator_id,
        invite_code=group.invite_code,
        is_public=group.is_public,
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=member_count,
        members=members,
        my_role=my_membership.role.value if my_membership else None,
        is_member=my_membership is not None,
    )


class GroupService:

    # ── Create ────────────────────────────────────────────────────────────────

    @staticmethod
    async def create(db: AsyncSession, user_id: int, data: CreateGroupRequest) -> GroupResponse:
        group = Group(
            name=data.name,
            description=data.description,
            creator_id=user_id,
            is_public=data.is_public,
        )
        db.add(group)
        await db.flush()

        # Creator is automatically admin
        db.add(GroupMember(group_id=group.id, user_id=user_id, role=GroupRole.admin))
        await db.flush()

        logger.info("Group created: %s (id=%d) by user=%d", group.name, group.id, user_id)
        return await _build_response(db, group, user_id)

    # ── Get ───────────────────────────────────────────────────────────────────

    @staticmethod
    async def get(db: AsyncSession, group_id: int, viewer_id: int) -> GroupResponse:
        group = await db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        if not group.is_public:
            membership = await _get_membership(db, group_id, viewer_id)
            if membership is None:
                raise HTTPException(status_code=403, detail="This group is private")

        return await _build_response(db, group, viewer_id)

    # ── List my groups ────────────────────────────────────────────────────────

    @staticmethod
    async def list_mine(db: AsyncSession, user_id: int) -> List[GroupResponse]:
        memberships = (await db.scalars(
            select(GroupMember)
            .where(GroupMember.user_id == user_id)
            .order_by(GroupMember.joined_at.desc())
        )).all()

        result = []
        for m in memberships:
            group = await db.get(Group, m.group_id)
            if group:
                result.append(await _build_response(db, group, user_id))
        return result

    # ── Discover ──────────────────────────────────────────────────────────────

    @staticmethod
    async def discover(db: AsyncSession, user_id: int, limit: int = 20) -> List[GroupResponse]:
        # Public groups the user hasn't joined
        joined_subq = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
        groups = (await db.scalars(
            select(Group)
            .where(Group.is_public == True, ~Group.id.in_(joined_subq))  # noqa: E712
            .order_by(Group.created_at.desc())
            .limit(limit)
        )).all()

        return [await _build_response(db, g, user_id) for g in groups]

    # ── Join by invite code ───────────────────────────────────────────────────

    @staticmethod
    async def join(db: AsyncSession, user_id: int, invite_code: str) -> GroupResponse:
        group = await db.scalar(
            select(Group).where(Group.invite_code == invite_code.upper())
        )
        if group is None:
            raise HTTPException(status_code=404, detail="Invalid invite code")

        existing = await _get_membership(db, group.id, user_id)
        if existing:
            raise HTTPException(status_code=409, detail="Already a member")

        db.add(GroupMember(group_id=group.id, user_id=user_id, role=GroupRole.member))
        await db.flush()

        # Broadcast
        await cache.publish(f"group:{group.id}", {
            "type": "member_joined",
            "user_id": user_id,
            "group_id": group.id,
        })

        return await _build_response(db, group, user_id)

    # ── Admin: invite user ────────────────────────────────────────────────────

    @staticmethod
    async def invite(db: AsyncSession, group_id: int, admin_id: int, target_user_id: int) -> GroupResponse:
        group = await db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        admin_membership = await _get_membership(db, group_id, admin_id)
        _require_admin(admin_membership)

        target_user = await db.get(User, target_user_id)
        if target_user is None:
            raise HTTPException(status_code=404, detail="Target user not found")

        existing = await _get_membership(db, group_id, target_user_id)
        if existing:
            raise HTTPException(status_code=409, detail="User is already a member")

        db.add(GroupMember(group_id=group_id, user_id=target_user_id, role=GroupRole.member))
        await db.flush()

        await cache.publish(f"group:{group_id}", {
            "type": "member_invited",
            "user_id": target_user_id,
            "group_id": group_id,
            "invited_by": admin_id,
        })

        return await _build_response(db, group, admin_id)

    # ── Admin: remove member ──────────────────────────────────────────────────

    @staticmethod
    async def remove_member(db: AsyncSession, group_id: int, admin_id: int, target_id: int) -> GroupResponse:
        group = await db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        if target_id == admin_id:
            raise HTTPException(status_code=400, detail="Use 'leave' to remove yourself")

        admin_membership = await _get_membership(db, group_id, admin_id)
        _require_admin(admin_membership)

        target_membership = await _get_membership(db, group_id, target_id)
        if target_membership is None:
            raise HTTPException(status_code=404, detail="Member not found in group")

        await db.delete(target_membership)
        await db.flush()

        await cache.publish(f"group:{group_id}", {
            "type": "member_removed",
            "user_id": target_id,
            "group_id": group_id,
        })

        return await _build_response(db, group, admin_id)

    # ── Admin: change role ────────────────────────────────────────────────────

    @staticmethod
    async def change_role(
        db: AsyncSession, group_id: int, admin_id: int, target_id: int, new_role: str
    ) -> GroupResponse:
        group = await db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        admin_membership = await _get_membership(db, group_id, admin_id)
        _require_admin(admin_membership)

        target_membership = await _get_membership(db, group_id, target_id)
        if target_membership is None:
            raise HTTPException(status_code=404, detail="Member not found")

        target_membership.role = GroupRole(new_role)
        await db.flush()

        return await _build_response(db, group, admin_id)

    # ── Leave / delete group ──────────────────────────────────────────────────

    @staticmethod
    async def leave(db: AsyncSession, group_id: int, user_id: int) -> None:
        membership = await _get_membership(db, group_id, user_id)
        if membership is None:
            raise HTTPException(status_code=404, detail="Not a member")

        # If last admin, refuse unless sole member
        if membership.role == GroupRole.admin:
            other_admins = await db.scalar(
                select(func.count()).select_from(GroupMember).where(
                    GroupMember.group_id == group_id,
                    GroupMember.role == GroupRole.admin,
                    GroupMember.user_id != user_id,
                )
            ) or 0
            member_count = await db.scalar(
                select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id)
            ) or 0
            if other_admins == 0 and member_count > 1:
                raise HTTPException(
                    status_code=400,
                    detail="Promote another member to admin before leaving",
                )

        await db.delete(membership)
        await db.flush()

        await cache.publish(f"group:{group_id}", {"type": "member_left", "user_id": user_id, "group_id": group_id})

    @staticmethod
    async def delete_group(db: AsyncSession, group_id: int, user_id: int) -> None:
        group = await db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        membership = await _get_membership(db, group_id, user_id)
        _require_admin(membership)

        await db.delete(group)
        await db.flush()

        await cache.publish(f"group:{group_id}", {"type": "group_deleted", "group_id": group_id})
