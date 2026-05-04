"""Closet item vector similarity helpers."""

from __future__ import annotations

from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.closet import ClosetItem

settings = get_settings()
logger = get_logger("similarity_service")


async def generate_item_embedding(item: ClosetItem) -> list[float]:
    description = f"{item.name} {item.category} {item.color or ''} {' '.join(item.tags or [])}".strip()
    if not settings.openai_api_key:
        logger.warning("embedding_fallback", reason="OPENAI_API_KEY not set", item_id=str(item.id))
        return [0.0] * 1536
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": settings.embedding_model, "input": description},
        )
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
    if len(vector) != 1536:
        raise ValueError(f"Embedding model returned {len(vector)} dimensions; expected 1536")
    return [float(v) for v in vector]


async def find_similar_items(session: AsyncSession, item_id: str, user_id: str, limit: int = 5) -> list[ClosetItem]:
    source = await session.get(ClosetItem, UUID(item_id))
    if source is None or source.user_id != UUID(user_id) or not source.embedding:
        return []
    result = await session.execute(
        select(ClosetItem)
        .where(
            ClosetItem.user_id == UUID(user_id),
            ClosetItem.id != UUID(item_id),
            ClosetItem.embedding.is_not(None),
        )
        .order_by(ClosetItem.embedding.cosine_distance(source.embedding))
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_item_embedding(session: AsyncSession, item_id: str) -> None:
    item = await session.get(ClosetItem, UUID(item_id))
    if item is None:
        return
    item.embedding = await generate_item_embedding(item)
    await session.commit()
