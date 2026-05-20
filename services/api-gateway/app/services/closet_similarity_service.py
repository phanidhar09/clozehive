"""Closet item similarity search service.

Finds similar items using text embeddings of item metadata.
Image-based similarity uses the item's text description as a fallback
(CLIP-based visual embeddings can be added later without changing the interface).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.closet import ClosetItem
from app.services.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
    vector_literal,
)
from app.services.similarity_service import generate_item_embedding, update_item_embedding_job

logger = get_logger("closet_similarity_service")


async def _ensure_item_embedding(session: AsyncSession, item: ClosetItem) -> list[float] | None:
    """Return the item's embedding, generating and persisting it if missing."""
    if item.embedding:
        return list(item.embedding)
    try:
        embedding = await generate_item_embedding(item)
        item.embedding = embedding
        await session.flush()
        return embedding
    except Exception as exc:
        logger.warning("ensure_embedding_failed", item_id=str(item.id), error=str(exc))
        return None


async def find_similar_by_item_id(
    session: AsyncSession,
    item_id: str,
    user_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Find closet items similar to a given item (by its text embedding)."""
    source = await session.get(ClosetItem, uuid.UUID(item_id))
    if not source or str(source.user_id) != user_id or source.is_archived:
        return []

    embedding = await _ensure_item_embedding(session, source)
    if not embedding:
        return []

    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=embedding,
        user_id=user_id,
        extra_where=f"AND id != '{item_id}'::uuid AND is_archived = false",
        limit=limit,
        threshold=0.65,
    )
    return _format_similarity_results(rows, "closet_item")


async def find_similar_by_text(
    session: AsyncSession,
    query: str,
    user_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Find closet items matching a text description."""
    embedding = await generate_text_embedding(query)
    if not embedding:
        return []

    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=embedding,
        user_id=user_id,
        extra_where="AND is_archived = false",
        limit=limit,
        threshold=0.60,
    )
    return _format_similarity_results(rows, "text_query")


async def find_similar_by_image_url(
    session: AsyncSession,
    image_url: str,
    user_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """
    Find items similar to an image URL.

    MVP fallback: generates a text embedding from the URL path to find items
    with similar metadata. Full CLIP-based image embedding can replace this later
    without changing the caller interface.
    """
    url_path = image_url.split("/")[-1]
    fallback_text = f"Image: {url_path}"
    return await find_similar_by_text(session, fallback_text, user_id, limit)


async def check_duplicate_on_upload(
    session: AsyncSession,
    user_id: str,
    item_metadata: dict[str, Any],
    threshold: float = 0.88,
) -> list[dict[str, Any]]:
    """
    Check if a newly uploaded/detected item already exists in the closet.
    Called during bulk ingest confirmation before saving.
    Returns potential duplicates with high similarity scores.
    """
    text = item_to_embedding_text(item_metadata)
    embedding = await generate_text_embedding(text)
    if not embedding:
        return []

    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=embedding,
        user_id=user_id,
        extra_where="AND is_archived = false",
        limit=3,
        threshold=threshold,
    )
    return _format_similarity_results(rows, "duplicate_check")


def _format_similarity_results(
    rows: list[dict[str, Any]],
    query_type: str,
) -> list[dict[str, Any]]:
    results = []
    for r in rows:
        score = float(r.get("similarity_score", 0))
        reason = _similarity_reason(score, r)
        results.append({
            "item_id": str(r["id"]),
            "name": r.get("name", ""),
            "category": r.get("category", ""),
            "color": r.get("color") or "",
            "brand": r.get("brand") or "",
            "image_url": r.get("image_url") or r.get("processed_image_url") or "",
            "similarity_score": round(score, 3),
            "reason": reason,
        })
    return results


def _similarity_reason(score: float, item: dict[str, Any]) -> str:
    cat = item.get("category", "item")
    color = item.get("color", "")
    if score >= 0.90:
        return f"Very similar {cat}" + (f" — {color}" if color else "")
    if score >= 0.80:
        return f"Similar {cat} — matching style and occasion"
    return f"Related {cat} — shares some attributes"
