"""
Social routes — /api/v1/social/*
User search, follow/unfollow, follower lists, groups.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.repositories.closet_repo import ClosetRepository
from app.repositories.social_repo import FollowRepository, GroupMemberRepository, GroupRepository
from app.repositories.user_repo import UserRepository
from app.schemas.social import (
    FollowResponse,
    GroupCreate,
    GroupMemberResponse,
    GroupResponse,
    GroupUpdate,
    JoinGroupRequest,
    PublicUserResponse,
    RoleUpdateRequest,
)
from app.services import cache_service

import secrets

logger = get_logger("social_routes")
router = APIRouter(prefix="/social", tags=["Social"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _build_public_user(
    db: DbSession,
    user_id_str: str,
    me_id: UUID,
    target_id: UUID,
) -> PublicUserResponse:
    users = UserRepository(db)
    follows = FollowRepository(db)
    closet = ClosetRepository(db)

    user = await users.get_or_raise(target_id)
    follower_count = await follows.follower_count(target_id)
    following_count = await follows.following_count(target_id)
    item_count = await closet.count_by_user(target_id)
    is_following = await follows.is_following(me_id, target_id)

    return PublicUserResponse(
        id=user.id,
        username=user.username,
        name=user.name,
        bio=user.bio,
        avatar_url=user.avatar_url,
        follower_count=follower_count,
        following_count=following_count,
        item_count=item_count,
        is_following=is_following,
    )


def _build_group_response(group, members_with_users, me_id: UUID) -> GroupResponse:
    members_resp = []
    my_role = None
    is_member = False

    for gm, u in members_with_users:
        members_resp.append(GroupMemberResponse(
            user_id=u.id,
            username=u.username,
            name=u.name,
            avatar_url=u.avatar_url,
            role=gm.role,
            joined_at=gm.joined_at,
        ))
        if u.id == me_id:
            my_role = gm.role
            is_member = True

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        owner_id=group.owner_id,
        is_private=group.is_private,
        invite_code=group.invite_code,
        avatar_url=group.avatar_url,
        member_count=len(members_resp),
        members=members_resp,
        my_role=my_role,
        is_member=is_member,
        created_at=group.created_at,
    )


# ── User search ───────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[PublicUserResponse])
async def search_users(
    user_id: CurrentUser,
    db: DbSession,
    q: str = Query("", max_length=100),
):
    users = UserRepository(db)
    me = UUID(user_id)
    if q:
        found = await users.search(q, exclude_id=me)
    else:
        found = await users.list(
            filters=[],
            order_by=[],
            limit=30,
        )
        found = [u for u in found if u.id != me][:30]

    result = []
    for u in found:
        result.append(await _build_public_user(db, user_id, me, u.id))
    return result


@router.get("/profile/{target_id}", response_model=PublicUserResponse)
async def get_profile(target_id: UUID, user_id: CurrentUser, db: DbSession):
    return await _build_public_user(db, user_id, UUID(user_id), target_id)


# ── Follow / unfollow ─────────────────────────────────────────────────────────

@router.post("/follow/{target_id}", response_model=FollowResponse)
async def follow(target_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    if target_id == me:
        raise BadRequestError("Cannot follow yourself")

    users = UserRepository(db)
    if not await users.exists(__import__("app.models.user", fromlist=["User"]).User.id == target_id):
        raise NotFoundError("User not found")

    follows = FollowRepository(db)
    if await follows.is_following(me, target_id):
        raise ConflictError("Already following this user")

    await follows.create(follower_id=me, following_id=target_id)
    count = await follows.follower_count(target_id)
    return FollowResponse(following=True, follower_count=count)


@router.delete("/follow/{target_id}", response_model=FollowResponse)
async def unfollow(target_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    follows = FollowRepository(db)
    existing = await follows.get(target_id)  # won't work — need compound PK query

    # Direct query using the composite PK
    from sqlalchemy import and_, delete
    from app.models.social import Follow
    await db.execute(
        delete(Follow).where(
            and_(Follow.follower_id == me, Follow.following_id == target_id)
        )
    )
    count = await follows.follower_count(target_id)
    return FollowResponse(following=False, follower_count=count)


@router.get("/followers/{target_id}", response_model=list[PublicUserResponse])
async def list_followers(target_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    follows = FollowRepository(db)
    users = await follows.get_followers(target_id)
    result = []
    for u in users:
        follower_count = await follows.follower_count(u.id)
        is_following = await follows.is_following(me, u.id)
        result.append(PublicUserResponse(
            id=u.id, username=u.username, name=u.name,
            bio=u.bio, avatar_url=u.avatar_url,
            follower_count=follower_count, following_count=0,
            item_count=0, is_following=is_following,
        ))
    return result


@router.get("/following/{target_id}", response_model=list[PublicUserResponse])
async def list_following(target_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    follows = FollowRepository(db)
    users = await follows.get_following(target_id)
    result = []
    for u in users:
        follower_count = await follows.follower_count(u.id)
        is_following = await follows.is_following(me, u.id)
        result.append(PublicUserResponse(
            id=u.id, username=u.username, name=u.name,
            bio=u.bio, avatar_url=u.avatar_url,
            follower_count=follower_count, following_count=0,
            item_count=0, is_following=is_following,
        ))
    return result


# ── Groups ────────────────────────────────────────────────────────────────────

@router.get("/groups", response_model=list[GroupResponse])
async def my_groups(user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    members_repo = GroupMemberRepository(db)
    groups = await groups_repo.get_user_groups(me)
    result = []
    for g in groups:
        mwu = await members_repo.get_members_with_users(g.id)
        result.append(_build_group_response(g, mwu, me))
    return result


@router.get("/groups/discover", response_model=list[GroupResponse])
async def discover_groups(user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    members_repo = GroupMemberRepository(db)
    groups = await groups_repo.get_public_groups(exclude_user_id=me)
    result = []
    for g in groups:
        mwu = await members_repo.get_members_with_users(g.id)
        result.append(_build_group_response(g, mwu, me))
    return result


@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(body: GroupCreate, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    members_repo = GroupMemberRepository(db)

    group = await groups_repo.create(
        owner_id=me,
        name=body.name,
        description=body.description,
        is_private=body.is_private,
        invite_code=secrets.token_urlsafe(8)[:10].upper(),
    )
    await members_repo.create(group_id=group.id, user_id=me, role="admin")
    mwu = await members_repo.get_members_with_users(group.id)
    return _build_group_response(group, mwu, me)


@router.post("/groups/join", response_model=GroupResponse)
async def join_group(body: JoinGroupRequest, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    members_repo = GroupMemberRepository(db)

    group = await groups_repo.get_by_invite_code(body.invite_code)
    if not group:
        raise NotFoundError("Invalid invite code")

    existing = await members_repo.get_membership(group.id, me)
    if existing:
        raise ConflictError("Already a member of this group")

    await members_repo.create(group_id=group.id, user_id=me, role="member")
    mwu = await members_repo.get_members_with_users(group.id)
    return _build_group_response(group, mwu, me)


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group(group_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    members_repo = GroupMemberRepository(db)
    group = await groups_repo.get_or_raise(group_id)
    mwu = await members_repo.get_members_with_users(group.id)
    return _build_group_response(group, mwu, me)


@router.patch("/groups/{group_id}/members/{target_uid}/role", response_model=dict)
async def change_member_role(
    group_id: UUID,
    target_uid: UUID,
    body: RoleUpdateRequest,
    user_id: CurrentUser,
    db: DbSession,
):
    me = UUID(user_id)
    members_repo = GroupMemberRepository(db)

    my_membership = await members_repo.get_membership(group_id, me)
    if not my_membership or my_membership.role != "admin":
        raise ForbiddenError("Only admins can change member roles")

    target = await members_repo.get_membership(group_id, target_uid)
    if not target:
        raise NotFoundError("Member not found in group")

    await members_repo.update(target, role=body.role)
    return {"updated": True, "user_id": str(target_uid), "role": body.role}


@router.delete("/groups/{group_id}/members/{target_uid}", status_code=204)
async def remove_member(
    group_id: UUID,
    target_uid: UUID,
    user_id: CurrentUser,
    db: DbSession,
):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    members_repo = GroupMemberRepository(db)

    group = await groups_repo.get_or_raise(group_id)
    my_membership = await members_repo.get_membership(group_id, me)

    if not my_membership or (my_membership.role != "admin" and me != target_uid):
        raise ForbiddenError("Insufficient permissions")
    if group.owner_id == target_uid:
        raise BadRequestError("Cannot remove the group owner")

    target = await members_repo.get_membership(group_id, target_uid)
    if not target:
        raise NotFoundError("Member not found")
    await members_repo.delete(target)


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(group_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_repo = GroupRepository(db)
    group = await groups_repo.get_or_raise(group_id)
    if group.owner_id != me:
        raise ForbiddenError("Only the group owner can delete this group")
    await groups_repo.delete(group)
