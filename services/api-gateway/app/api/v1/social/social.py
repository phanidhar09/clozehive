"""
Social routes — /api/v1/social/*
User search, follow/unfollow, follower lists, groups.

User profiles → Postgres (UserRepository)
Follows + Groups → Firestore (FirestoreFollowService / FirestoreGroupService)
Closet item counts → Firestore (FirestoreClosetService)
"""

from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.social.schemas.social import (
    FollowResponse,
    GroupCreate,
    GroupMemberResponse,
    GroupResponse,
    JoinGroupRequest,
    PublicUserResponse,
    RoleUpdateRequest,
)
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.services.firestore.closet_service import FirestoreClosetService
from app.services.firestore.social_service import (
    FirestoreFollowService,
    FirestoreGroupMemberService,
    FirestoreGroupService,
)

logger = get_logger("social_routes")
router = APIRouter(prefix="/social", tags=["Social"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _build_public_user(
    db: DbSession,
    me_id: UUID,
    target_id: UUID,
) -> PublicUserResponse:
    users = UserRepository(db)
    follows = FirestoreFollowService()
    closet = FirestoreClosetService()

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


async def _build_group_response(
    group: dict,
    members: list[dict],
    db: DbSession,
    me_id: UUID,
) -> GroupResponse:
    users_repo = UserRepository(db)
    member_user_ids = [UUID(m["user_id"]) for m in members]

    user_map = {}
    for uid in member_user_ids:
        try:
            u = await users_repo.get_or_raise(uid)
            user_map[uid] = u
        except NotFoundError:
            pass

    members_resp = []
    my_role = None
    is_member = False

    for m in members:
        uid = UUID(m["user_id"])
        member_user = user_map.get(uid)
        if member_user is None:
            continue
        members_resp.append(
            GroupMemberResponse(
                user_id=member_user.id,
                username=member_user.username,
                name=member_user.name,
                avatar_url=member_user.avatar_url,
                role=m["role"],
                joined_at=m["joined_at"],
            )
        )
        if uid == me_id:
            my_role = m["role"]
            is_member = True

    return GroupResponse(
        id=UUID(group["id"]),
        name=group["name"],
        description=group.get("description"),
        owner_id=UUID(group["owner_id"]),
        is_private=group["is_private"],
        invite_code=group["invite_code"],
        avatar_url=group.get("avatar_url"),
        member_count=len(members_resp),
        members=members_resp,
        my_role=my_role,
        is_member=is_member,
        created_at=group["created_at"],
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
        found = await users.list(filters=[], order_by=[], limit=30)
        found = [u for u in found if u.id != me][:30]

    result = []
    for u in found:
        result.append(await _build_public_user(db, me, u.id))
    return result


# Route used by the frontend: GET /social/users/{user_id}
@router.get("/users/{target_id}", response_model=PublicUserResponse)
async def get_user_profile(target_id: UUID, user_id: CurrentUser, db: DbSession):
    """Get a user's public profile. Alias of /profile/{target_id} for frontend compatibility."""
    return await _build_public_user(db, UUID(user_id), target_id)


# Route used by the frontend: GET /social/users/{user_id}/followers
@router.get("/users/{target_id}/followers", response_model=list[PublicUserResponse])
async def get_user_followers(target_id: UUID, user_id: CurrentUser, db: DbSession):
    return await _list_followers(target_id, user_id, db)


# Route used by the frontend: GET /social/users/{user_id}/following
@router.get("/users/{target_id}/following", response_model=list[PublicUserResponse])
async def get_user_following(target_id: UUID, user_id: CurrentUser, db: DbSession):
    return await _list_following(target_id, user_id, db)


# Canonical routes kept for backward compatibility
@router.get("/profile/{target_id}", response_model=PublicUserResponse)
async def get_profile(target_id: UUID, user_id: CurrentUser, db: DbSession):
    return await _build_public_user(db, UUID(user_id), target_id)


# ── Follow / unfollow ─────────────────────────────────────────────────────────


@router.post("/follow/{target_id}", response_model=FollowResponse)
async def follow(target_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    if target_id == me:
        raise BadRequestError("Cannot follow yourself")

    users = UserRepository(db)
    target_user = await users.get(target_id)
    if not target_user:
        raise NotFoundError("User not found")

    follows = FirestoreFollowService()
    if await follows.is_following(me, target_id):
        raise ConflictError("Already following this user")

    await follows.follow(me, target_id)
    count = await follows.follower_count(target_id)
    return FollowResponse(following=True, follower_count=count)


@router.delete("/follow/{target_id}", response_model=FollowResponse)
async def unfollow(target_id: UUID, user_id: CurrentUser):
    me = UUID(user_id)
    follows = FirestoreFollowService()
    await follows.unfollow(me, target_id)
    count = await follows.follower_count(target_id)
    return FollowResponse(following=False, follower_count=count)


async def _list_followers(
    target_id: UUID,
    user_id: CurrentUser,
    db: DbSession,
    limit: int = 50,
    offset: int = 0,
) -> list[PublicUserResponse]:
    me = UUID(user_id)
    follows = FirestoreFollowService()
    all_ids = await follows.get_follower_ids(target_id)
    page_ids = all_ids[offset : offset + limit]
    users_repo = UserRepository(db)
    result = []
    for uid in page_ids:
        try:
            u = await users_repo.get_or_raise(uid)
            f_count = await follows.follower_count(uid)
            is_fol = await follows.is_following(me, uid)
            result.append(
                PublicUserResponse(
                    id=u.id,
                    username=u.username,
                    name=u.name,
                    bio=u.bio,
                    avatar_url=u.avatar_url,
                    follower_count=f_count,
                    following_count=0,
                    item_count=0,
                    is_following=is_fol,
                )
            )
        except NotFoundError:
            pass
    return result


async def _list_following(
    target_id: UUID,
    user_id: CurrentUser,
    db: DbSession,
    limit: int = 50,
    offset: int = 0,
) -> list[PublicUserResponse]:
    me = UUID(user_id)
    follows = FirestoreFollowService()
    all_ids = await follows.get_following_ids(target_id)
    page_ids = all_ids[offset : offset + limit]
    users_repo = UserRepository(db)
    result = []
    for uid in page_ids:
        try:
            u = await users_repo.get_or_raise(uid)
            f_count = await follows.follower_count(uid)
            is_fol = await follows.is_following(me, uid)
            result.append(
                PublicUserResponse(
                    id=u.id,
                    username=u.username,
                    name=u.name,
                    bio=u.bio,
                    avatar_url=u.avatar_url,
                    follower_count=f_count,
                    following_count=0,
                    item_count=0,
                    is_following=is_fol,
                )
            )
        except NotFoundError:
            pass
    return result


@router.get("/followers/{target_id}", response_model=list[PublicUserResponse])
async def list_followers(
    target_id: UUID,
    user_id: CurrentUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await _list_followers(target_id, user_id, db, limit=limit, offset=offset)


@router.get("/following/{target_id}", response_model=list[PublicUserResponse])
async def list_following(
    target_id: UUID,
    user_id: CurrentUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await _list_following(target_id, user_id, db, limit=limit, offset=offset)


# ── Groups ────────────────────────────────────────────────────────────────────


@router.get("/groups", response_model=list[GroupResponse])
async def my_groups(user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()
    groups = await groups_svc.get_user_groups(me)
    result = []
    for g in groups:
        members = await members_svc.get_members(UUID(g["id"]))
        result.append(await _build_group_response(g, members, db, me))
    return result


@router.get("/groups/discover", response_model=list[GroupResponse])
async def discover_groups(user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()
    groups = await groups_svc.get_public_groups(exclude_user_id=me)
    result = []
    for g in groups:
        members = await members_svc.get_members(UUID(g["id"]))
        result.append(await _build_group_response(g, members, db, me))
    return result


@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(body: GroupCreate, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()

    group = await groups_svc.create_group(
        owner_id=me,
        name=body.name,
        description=body.description,
        is_private=body.is_private,
        invite_code=secrets.token_urlsafe(8)[:10].upper(),
    )
    member = await members_svc.add_member(UUID(group["id"]), me, role="admin")
    return await _build_group_response(group, [member], db, me)


@router.post("/groups/join", response_model=GroupResponse)
async def join_group(body: JoinGroupRequest, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()

    group = await groups_svc.get_by_invite_code(body.invite_code)
    if not group:
        raise NotFoundError("Invalid invite code")

    group_id = UUID(group["id"])
    existing = await members_svc.get_membership(group_id, me)
    if existing:
        raise ConflictError("Already a member of this group")

    await members_svc.add_member(group_id, me, role="member")
    members = await members_svc.get_members(group_id)
    return await _build_group_response(group, members, db, me)


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group(group_id: UUID, user_id: CurrentUser, db: DbSession):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()
    group = await groups_svc.get_group(group_id)
    members = await members_svc.get_members(group_id)
    return await _build_group_response(group, members, db, me)


@router.patch("/groups/{group_id}/members/{target_uid}/role", response_model=dict)
async def change_member_role(
    group_id: UUID,
    target_uid: UUID,
    body: RoleUpdateRequest,
    user_id: CurrentUser,
):
    me = UUID(user_id)
    members_svc = FirestoreGroupMemberService()

    my_membership = await members_svc.get_membership(group_id, me)
    if not my_membership or my_membership["role"] != "admin":
        raise ForbiddenError("Only admins can change member roles")

    target = await members_svc.get_membership(group_id, target_uid)
    if not target:
        raise NotFoundError("Member not found in group")

    await members_svc.update_role(group_id, target_uid, body.role)
    return {"updated": True, "user_id": str(target_uid), "role": body.role}


@router.delete("/groups/{group_id}/members/me", status_code=204)
async def leave_group(group_id: UUID, user_id: CurrentUser):
    """Leave a group (self-removal)."""
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()

    group = await groups_svc.get_group(group_id)
    if group["owner_id"] == str(me):
        raise BadRequestError("Group owner cannot leave — delete the group instead")

    membership = await members_svc.get_membership(group_id, me)
    if not membership:
        raise NotFoundError("You are not a member of this group")

    await members_svc.remove_member(group_id, me)


@router.delete("/groups/{group_id}/members/{target_uid}", status_code=204)
async def remove_member(
    group_id: UUID,
    target_uid: UUID,
    user_id: CurrentUser,
):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    members_svc = FirestoreGroupMemberService()

    group = await groups_svc.get_group(group_id)
    my_membership = await members_svc.get_membership(group_id, me)

    if not my_membership or (my_membership["role"] != "admin" and me != target_uid):
        raise ForbiddenError("Insufficient permissions")
    if group["owner_id"] == str(target_uid):
        raise BadRequestError("Cannot remove the group owner")

    target = await members_svc.get_membership(group_id, target_uid)
    if not target:
        raise NotFoundError("Member not found")
    await members_svc.remove_member(group_id, target_uid)


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(group_id: UUID, user_id: CurrentUser):
    me = UUID(user_id)
    groups_svc = FirestoreGroupService()
    group = await groups_svc.get_group(group_id)
    if group["owner_id"] != str(me):
        raise ForbiddenError("Only the group owner can delete this group")
    await groups_svc.delete_group(group_id)
