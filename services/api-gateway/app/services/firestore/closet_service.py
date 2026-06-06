"""
Firestore-backed closet service.

Collection: closet_items
Document ID: {uuid} (string)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from google.cloud import firestore
from google.cloud.firestore_v1 import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.api.v1.wardrobe.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    ClosetListResponse,
)
from app.core import cache_service
from app.services.firestore.firestore_client import get_db

logger = get_logger("firestore.closet")

_COLLECTION = "closet_items"


def _now() -> datetime:
    return datetime.now(UTC)


def _date_to_str(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _str_to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _doc_to_dict(doc_data: dict[str, Any]) -> dict[str, Any]:
    """Normalise raw Firestore data into a form Pydantic can validate."""
    d = dict(doc_data)
    # UUIDs are stored as strings
    d["id"] = UUID(d["id"]) if isinstance(d.get("id"), str) else d.get("id")
    d["user_id"] = UUID(d["user_id"]) if isinstance(d.get("user_id"), str) else d.get("user_id")

    # Firestore Timestamps are already datetime objects (DatetimeWithNanoseconds)
    # but they may be timezone-naive; ensure they're UTC-aware
    for ts_field in ("created_at", "updated_at"):
        v = d.get(ts_field)
        if isinstance(v, datetime) and v.tzinfo is None:
            d[ts_field] = v.replace(tzinfo=UTC)

    # last_worn is stored as "YYYY-MM-DD" string
    d["last_worn"] = _str_to_date(d.get("last_worn"))

    # Ensure numeric defaults
    d.setdefault("wear_count", 0)
    d.setdefault("is_archived", False)

    return d


def _to_response(doc_data: dict[str, Any]) -> ClosetItemResponse:
    return ClosetItemResponse.model_validate(_doc_to_dict(doc_data))


class FirestoreClosetService:
    """Stateless — no session needed; uses module-level Firestore client."""

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_items(
        self,
        user_id: UUID,
        *,
        section: str | None = None,
        category: str | None = None,
        season: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> ClosetListResponse:
        uid = str(user_id)
        cache_key = cache_service.build_closet_cache_key(
            uid,
            {"category": category, "page": page, "per_page": per_page, "season": season, "section": section},
        )
        cached = await cache_service.get(cache_key)
        if cached:
            return ClosetListResponse(**cached)

        db = get_db()
        query = (
            db.collection(_COLLECTION)
            .where(filter=FieldFilter("user_id", "==", uid))
            .where(filter=FieldFilter("is_archived", "==", False))
        )
        if section:
            query = query.where(filter=FieldFilter("section", "==", section))
        if category:
            query = query.where(filter=FieldFilter("category", "==", category))
        if season:
            query = query.where(filter=FieldFilter("season", "==", season))

        query = query.order_by("created_at", direction="DESCENDING")

        # Firestore doesn't support SQL-style OFFSET, so we fetch all and slice
        all_docs: list[dict[str, Any]] = []
        async for doc in query.stream():
            all_docs.append(doc.to_dict())

        total = len(all_docs)
        offset = (page - 1) * per_page
        page_docs = all_docs[offset : offset + per_page]
        items = [_to_response(d) for d in page_docs]

        response = ClosetListResponse(items=items, total=total, page=page, per_page=per_page)

        from app.core.config import get_settings
        ttl = get_settings().cache_ttl_closet
        await cache_service.set(cache_key, response.model_dump(mode="json"), ttl)

        return response

    # ── Count ─────────────────────────────────────────────────────────────────

    async def count_by_user(self, user_id: UUID) -> int:
        db = get_db()
        query = (
            db.collection(_COLLECTION)
            .where(filter=FieldFilter("user_id", "==", str(user_id)))
            .where(filter=FieldFilter("is_archived", "==", False))
        )
        count = 0
        async for _ in query.stream():
            count += 1
        return count

    # ── Get one ───────────────────────────────────────────────────────────────

    async def get_item(self, item_id: UUID, user_id: UUID) -> ClosetItemResponse:
        db = get_db()
        doc = await db.collection(_COLLECTION).document(str(item_id)).get()
        if not doc.exists:
            raise NotFoundError(f"Item {item_id} not found")
        data = doc.to_dict()
        if data.get("user_id") != str(user_id):
            raise ForbiddenError("Item does not belong to you")
        return _to_response(data)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_item(self, user_id: UUID, data: ClosetItemCreate) -> ClosetItemResponse:
        db = get_db()
        item_id = uuid.uuid4()
        now = _now()
        doc_data: dict[str, Any] = {
            "id": str(item_id),
            "user_id": str(user_id),
            **data.model_dump(),
            "wear_count": 0,
            "last_worn": None,
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
        }
        # occasion and tags default to [] if None
        doc_data.setdefault("occasion", [])
        doc_data.setdefault("tags", [])

        await db.collection(_COLLECTION).document(str(item_id)).set(doc_data)
        await cache_service.invalidate_closet_list_cache(str(user_id))
        logger.info("closet_item_created", user_id=str(user_id), item_id=str(item_id))
        return _to_response(doc_data)

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_item(
        self, item_id: UUID, user_id: UUID, data: ClosetItemUpdate
    ) -> ClosetItemResponse:
        db = get_db()
        ref = db.collection(_COLLECTION).document(str(item_id))
        doc = await ref.get()
        if not doc.exists:
            raise NotFoundError(f"Item {item_id} not found")
        stored = doc.to_dict()
        if stored.get("user_id") != str(user_id):
            raise ForbiddenError("Item does not belong to you")

        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        updates["updated_at"] = _now()
        await ref.update(updates)

        merged = {**stored, **updates}
        return _to_response(merged)

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_item(self, item_id: UUID, user_id: UUID) -> None:
        db = get_db()
        ref = db.collection(_COLLECTION).document(str(item_id))
        doc = await ref.get()
        if not doc.exists:
            raise NotFoundError(f"Item {item_id} not found")
        if doc.to_dict().get("user_id") != str(user_id):
            raise ForbiddenError("Item does not belong to you")
        await ref.delete()
        await cache_service.invalidate_closet_list_cache(str(user_id))
        logger.info("closet_item_deleted", user_id=str(user_id), item_id=str(item_id))

    # ── Wear log ──────────────────────────────────────────────────────────────

    async def log_wear(
        self, item_id: UUID, user_id: UUID, worn_date: date | None = None
    ) -> ClosetItemResponse:
        db = get_db()
        ref = db.collection(_COLLECTION).document(str(item_id))
        doc = await ref.get()
        if not doc.exists:
            raise NotFoundError(f"Item {item_id} not found")
        stored = doc.to_dict()
        if stored.get("user_id") != str(user_id):
            raise ForbiddenError("Item does not belong to you")

        new_count = (stored.get("wear_count") or 0) + 1
        updates = {
            "wear_count": new_count,
            "last_worn": _date_to_str(worn_date or date.today()),
            "updated_at": _now(),
        }
        await ref.update(updates)
        await cache_service.invalidate_closet_list_cache(str(user_id))

        merged = {**stored, **updates}
        return _to_response(merged)

    # ── Bulk fetch for AI context ─────────────────────────────────────────────

    async def get_all_for_ai(self, user_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
        """Return a lightweight list of closet items for AI prompt context."""
        db = get_db()
        query = (
            db.collection(_COLLECTION)
            .where(filter=FieldFilter("user_id", "==", str(user_id)))
            .where(filter=FieldFilter("is_archived", "==", False))
            .limit(limit)
        )
        result = []
        async for doc in query.stream():
            d = doc.to_dict()
            result.append({
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "category": d.get("category", ""),
                "color": d.get("color") or "",
                "fabric": d.get("fabric") or "",
                "season": d.get("season") or "",
                "occasion": d.get("occasion") or [],
                "tags": d.get("tags") or [],
            })
        return result
