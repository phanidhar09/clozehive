"""
Firestore-backed social service — follows and groups.

Collections:
  follows        → {follower_id}_{following_id}
  groups         → {group_id}
  group_members  → {group_id}_{user_id}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.services.firestore.firestore_client import get_db

logger = get_logger("firestore.social")

_FOLLOWS = "follows"
_GROUPS = "groups"
_GROUP_MEMBERS = "group_members"


def _now() -> datetime:
    return datetime.now(UTC)


def _follow_doc_id(follower_id: UUID, following_id: UUID) -> str:
    return f"{follower_id}_{following_id}"


def _member_doc_id(group_id: UUID, user_id: UUID) -> str:
    return f"{group_id}_{user_id}"


# ── Follows ───────────────────────────────────────────────────────────────────


class FirestoreFollowService:
    async def follow(self, follower_id: UUID, following_id: UUID) -> None:
        db = get_db()
        doc_id = _follow_doc_id(follower_id, following_id)
        await (
            db.collection(_FOLLOWS)
            .document(doc_id)
            .set(
                {
                    "follower_id": str(follower_id),
                    "following_id": str(following_id),
                    "created_at": _now(),
                }
            )
        )

    async def unfollow(self, follower_id: UUID, following_id: UUID) -> None:
        db = get_db()
        doc_id = _follow_doc_id(follower_id, following_id)
        await db.collection(_FOLLOWS).document(doc_id).delete()

    async def is_following(self, follower_id: UUID, following_id: UUID) -> bool:
        db = get_db()
        doc_id = _follow_doc_id(follower_id, following_id)
        doc = await db.collection(_FOLLOWS).document(doc_id).get()
        return doc.exists

    async def follower_count(self, user_id: UUID) -> int:
        db = get_db()
        query = db.collection(_FOLLOWS).where(filter=FieldFilter("following_id", "==", str(user_id)))
        count = 0
        async for _ in query.stream():
            count += 1
        return count

    async def following_count(self, user_id: UUID) -> int:
        db = get_db()
        query = db.collection(_FOLLOWS).where(filter=FieldFilter("follower_id", "==", str(user_id)))
        count = 0
        async for _ in query.stream():
            count += 1
        return count

    async def get_follower_ids(self, user_id: UUID) -> list[UUID]:
        """Return UUIDs of users who follow user_id."""
        db = get_db()
        query = db.collection(_FOLLOWS).where(filter=FieldFilter("following_id", "==", str(user_id)))
        ids = []
        async for doc in query.stream():
            d = doc.to_dict()
            ids.append(UUID(d["follower_id"]))
        return ids

    async def get_following_ids(self, user_id: UUID) -> list[UUID]:
        """Return UUIDs of users that user_id follows."""
        db = get_db()
        query = db.collection(_FOLLOWS).where(filter=FieldFilter("follower_id", "==", str(user_id)))
        ids = []
        async for doc in query.stream():
            d = doc.to_dict()
            ids.append(UUID(d["following_id"]))
        return ids


# ── Groups ────────────────────────────────────────────────────────────────────


class FirestoreGroupService:
    async def create_group(
        self,
        owner_id: UUID,
        name: str,
        description: str | None,
        is_private: bool,
        invite_code: str,
    ) -> dict[str, Any]:
        db = get_db()
        group_id = uuid.uuid4()
        now = _now()
        doc: dict[str, Any] = {
            "id": str(group_id),
            "owner_id": str(owner_id),
            "name": name,
            "description": description,
            "is_private": is_private,
            "invite_code": invite_code,
            "avatar_url": None,
            "created_at": now,
        }
        await db.collection(_GROUPS).document(str(group_id)).set(doc)
        return doc

    async def get_group(self, group_id: UUID) -> dict[str, Any]:
        db = get_db()
        doc = await db.collection(_GROUPS).document(str(group_id)).get()
        if not doc.exists:
            raise NotFoundError(f"Group {group_id} not found")
        return doc.to_dict()

    async def get_by_invite_code(self, invite_code: str) -> dict[str, Any] | None:
        db = get_db()
        query = db.collection(_GROUPS).where(filter=FieldFilter("invite_code", "==", invite_code)).limit(1)
        async for doc in query.stream():
            return doc.to_dict()
        return None

    async def get_user_groups(self, user_id: UUID) -> list[dict[str, Any]]:
        """Return groups where user_id is a member."""
        db = get_db()
        member_query = db.collection(_GROUP_MEMBERS).where(filter=FieldFilter("user_id", "==", str(user_id)))
        group_ids = []
        async for doc in member_query.stream():
            group_ids.append(doc.to_dict()["group_id"])

        groups = []
        for gid in group_ids:
            try:
                g = await self.get_group(UUID(gid))
                groups.append(g)
            except NotFoundError:
                pass
        return groups

    async def get_public_groups(self, exclude_user_id: UUID) -> list[dict[str, Any]]:
        """Return public groups where exclude_user_id is NOT a member."""
        db = get_db()
        query = db.collection(_GROUPS).where(filter=FieldFilter("is_private", "==", False)).limit(50)

        # Get groups user is already in to exclude them
        user_member_query = db.collection(_GROUP_MEMBERS).where(
            filter=FieldFilter("user_id", "==", str(exclude_user_id))
        )
        my_group_ids: set[str] = set()
        async for doc in user_member_query.stream():
            my_group_ids.add(doc.to_dict()["group_id"])

        groups = []
        async for doc in query.stream():
            d = doc.to_dict()
            if d["id"] not in my_group_ids:
                groups.append(d)
        return groups

    async def delete_group(self, group_id: UUID) -> None:
        db = get_db()
        # Delete all members first
        member_query = db.collection(_GROUP_MEMBERS).where(filter=FieldFilter("group_id", "==", str(group_id)))
        async for doc in member_query.stream():
            await doc.reference.delete()
        await db.collection(_GROUPS).document(str(group_id)).delete()


class FirestoreGroupMemberService:
    async def add_member(self, group_id: UUID, user_id: UUID, role: str = "member") -> dict[str, Any]:
        db = get_db()
        doc_id = _member_doc_id(group_id, user_id)
        now = _now()
        data: dict[str, Any] = {
            "group_id": str(group_id),
            "user_id": str(user_id),
            "role": role,
            "joined_at": now,
        }
        await db.collection(_GROUP_MEMBERS).document(doc_id).set(data)
        return data

    async def get_membership(self, group_id: UUID, user_id: UUID) -> dict[str, Any] | None:
        db = get_db()
        doc = await db.collection(_GROUP_MEMBERS).document(_member_doc_id(group_id, user_id)).get()
        return doc.to_dict() if doc.exists else None

    async def update_role(self, group_id: UUID, user_id: UUID, role: str) -> None:
        db = get_db()
        ref = db.collection(_GROUP_MEMBERS).document(_member_doc_id(group_id, user_id))
        await ref.update({"role": role})

    async def remove_member(self, group_id: UUID, user_id: UUID) -> None:
        db = get_db()
        await db.collection(_GROUP_MEMBERS).document(_member_doc_id(group_id, user_id)).delete()

    async def get_members(self, group_id: UUID) -> list[dict[str, Any]]:
        """Return all member records for a group."""
        db = get_db()
        query = db.collection(_GROUP_MEMBERS).where(filter=FieldFilter("group_id", "==", str(group_id)))
        members = []
        async for doc in query.stream():
            members.append(doc.to_dict())
        return members
