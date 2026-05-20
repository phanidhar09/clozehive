"""Shared embedding service used by all RAG features.

Provides:
- generate_text_embedding(text)  — OpenAI text-embedding-ada-002
- item_to_embedding_text(item)   — normalise closet item metadata to searchable text
- cosine_search(session, model, limit, threshold, vector)  — generic pgvector search
"""

from __future__ import annotations

from typing import Any, Type, TypeVar

from langsmith import traceable
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.db.base import Base

settings = get_settings()
logger = get_logger("embedding_service")

_client: AsyncOpenAI | None = None

_EMBEDDING_DIM = 1536
_DEFAULT_LIMIT = 5
_DEFAULT_THRESHOLD = 0.70

M = TypeVar("M", bound=Base)


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        )
    return _client


@traceable(name="rag_embed_text", run_type="embedding")
async def generate_text_embedding(text_input: str) -> list[float] | None:
    """Return a 1536-dim embedding or None when OpenAI is unavailable."""
    if not settings.openai_api_key or not text_input.strip():
        return None
    try:
        response = await _get_client().embeddings.create(
            model=settings.embedding_model,
            input=text_input[:8000],
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("embedding_failed", error=str(exc))
        return None


def item_to_embedding_text(item: dict[str, Any]) -> str:
    """Normalise closet item metadata into a single searchable string."""
    parts = [
        f"Category: {item.get('category', '')}",
        f"Name: {item.get('name', '')}",
    ]
    if item.get("color"):
        parts.append(f"Color: {item['color']}")
    if item.get("fabric"):
        parts.append(f"Material: {item['fabric']}")
    if item.get("pattern"):
        parts.append(f"Pattern: {item['pattern']}")
    seasons = item.get("season") or []
    if isinstance(seasons, list) and seasons:
        parts.append(f"Season: {', '.join(seasons)}")
    elif isinstance(seasons, str) and seasons:
        parts.append(f"Season: {seasons}")
    occasions = item.get("occasion") or []
    if isinstance(occasions, list) and occasions:
        parts.append(f"Occasions: {', '.join(occasions)}")
    tags = item.get("tags") or []
    if isinstance(tags, list) and tags:
        parts.append(f"Tags: {', '.join(tags)}")
    if item.get("notes"):
        parts.append(f"Description: {item['notes']}")
    if item.get("brand"):
        parts.append(f"Brand: {item['brand']}")
    return ". ".join(p for p in parts if p.split(": ", 1)[-1].strip()) + "."


def vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def pgvector_cosine_search(
    session: AsyncSession,
    table: str,
    embedding: list[float],
    user_id: str | None,
    extra_where: str = "",
    limit: int = _DEFAULT_LIMIT,
    threshold: float = _DEFAULT_THRESHOLD,
) -> list[dict[str, Any]]:
    """Raw SQL cosine search against any table with an `embedding` vector column."""
    vec = vector_literal(embedding)
    user_filter = f"AND user_id = '{user_id}'::uuid" if user_id else ""
    resolved_filter = "AND resolved = false" if table == "purchase_gaps" else ""
    sql = text(f"""
        SELECT *, 1 - (embedding <=> '{vec}'::vector) AS similarity_score
        FROM {table}
        WHERE embedding IS NOT NULL
          {user_filter}
          {extra_where}
          {resolved_filter}
          AND 1 - (embedding <=> '{vec}'::vector) >= :threshold
        ORDER BY embedding <=> '{vec}'::vector
        LIMIT :limit
    """)
    try:
        result = await session.execute(sql, {"threshold": threshold, "limit": limit})
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("pgvector_search_failed", table=table, error=str(exc))
        return []
