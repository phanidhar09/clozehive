"""Vector retrieval adapter for AI orchestration.

The agent stays stateless: embeddings live in Postgres/pgvector and this module
only retrieves relevant wardrobe context for a request.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog
from openai import AsyncOpenAI

from app.core.config import get_settings

logger = structlog.get_logger("vector_store")
settings = get_settings()

_pool: asyncpg.Pool | None = None
_openai: AsyncOpenAI | None = None


def _postgres_url() -> str:
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://"):]
    return url


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_postgres_url(),
            min_size=1,
            max_size=4,
            command_timeout=5,
        )
    return _pool


def get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


async def close() -> None:
    global _pool, _openai
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _openai is not None:
        await _openai.close()
        _openai = None


async def embed_query(text: str) -> list[float]:
    response = await get_openai().embeddings.create(
        model=settings.openai_embedding_model,
        input=text,
    )
    return response.data[0].embedding


async def search_closet_context(user_id: str, query: str) -> list[dict[str, Any]]:
    """Return semantically relevant closet items for prompt grounding."""
    if settings.vector_store != "pgvector" or not settings.openai_api_key:
        return []

    try:
        embedding = await embed_query(query)
        vector_literal = "[" + ",".join(str(x) for x in embedding) + "]"
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT closet_item_id, content, metadata, 1 - (embedding <=> $2::vector) AS score
                FROM closet_item_embeddings
                WHERE user_id = $1::uuid
                  AND 1 - (embedding <=> $2::vector) >= $3
                ORDER BY embedding <=> $2::vector
                LIMIT $4
                """,
                user_id,
                vector_literal,
                settings.vector_score_threshold,
                settings.vector_search_limit,
            )
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("vector_search_unavailable", error=str(exc))
        return []
