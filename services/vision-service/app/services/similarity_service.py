"""Closet item vector similarity helpers for vision-service."""

from __future__ import annotations

from uuid import UUID

from langsmith import traceable
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.db.session import AsyncSessionLocal
from app.models.closet import ClosetItem

settings = get_settings()
logger = get_logger("similarity_service")

_emb_client: AsyncOpenAI | None = None


def _embedding_client() -> AsyncOpenAI:
    global _emb_client
    if _emb_client is None:
        _emb_client = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        )
    return _emb_client


@traceable(name="vision_openai_embedding", run_type="embedding")
async def generate_item_embedding(item: ClosetItem) -> list[float]:
    description = f"{item.name} {item.category} {item.color or ''} {' '.join(item.tags or [])}".strip()
    if not settings.openai_api_key:
        logger.warning("embedding_fallback", reason="OPENAI_API_KEY not set", item_id=str(item.id))
        return [0.0] * 1536
    response = await _embedding_client().embeddings.create(
        model=settings.embedding_model,
        input=description,
        timeout=20.0,
    )
    vector = response.data[0].embedding
    if len(vector) != 1536:
        raise ValueError(f"Embedding model returned {len(vector)} dimensions; expected 1536")
    return [float(v) for v in vector]


async def update_item_embedding_job(item_id: str) -> None:
    """
    Background-safe embedding update: opens its own session and commits.
    """
    async with AsyncSessionLocal() as session:
        try:
            item = await session.get(ClosetItem, UUID(item_id))
            if item is None:
                return
            item.embedding = await generate_item_embedding(item)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
