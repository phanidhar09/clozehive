"""Shared embedding service used by all RAG features.

Provides:
- generate_text_embedding(text)  — OpenAI text-embedding-ada-002
- item_to_embedding_text(item)   — normalise closet item metadata to searchable text
- cosine_search(session, model, limit, threshold, vector)  — generic pgvector search
"""

from __future__ import annotations

import re
import uuid as _uuid
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

# Tables that are permitted as targets for pgvector_cosine_search.
# This allowlist prevents table-name injection — PostgreSQL cannot parameterise
# table/column identifiers, so we validate the caller-supplied name explicitly.
_ALLOWED_TABLES: frozenset[str] = frozenset({
    "closet_items",
    "outfit_history",
    "packing_memory",
    "fashion_knowledge_documents",
    "purchase_gaps",
})

# Matches the exact string produced by vector_literal(): "[f,f,f,…]"
_VEC_RE = re.compile(r"\[[\d.,eE+\-]+\]")

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
    limit: int = _DEFAULT_LIMIT,
    threshold: float = _DEFAULT_THRESHOLD,
    filter_archived: bool = False,
    exclude_id: str | None = None,
    filter_category: str | None = None,
) -> list[dict[str, Any]]:
    """Raw SQL cosine search against any table with an `embedding` vector column.

    Security notes:
    - ``table`` is validated against ``_ALLOWED_TABLES`` (cannot be parameterised
      in PostgreSQL; must use an allowlist).
    - The vector literal is validated with a strict regex before interpolation.
    - All user-supplied filter values (``user_id``, ``exclude_id``,
      ``filter_category``) are passed as bound parameters, never interpolated.
    """
    if table not in _ALLOWED_TABLES:
        logger.warning("pgvector_search_blocked", table=table, reason="table_not_in_allowlist")
        return []

    vec = vector_literal(embedding)
    if not _VEC_RE.fullmatch(vec):
        logger.warning("pgvector_search_blocked", reason="invalid_vector_literal")
        return []

    if exclude_id is not None:
        try:
            _uuid.UUID(exclude_id)
        except ValueError:
            logger.warning("pgvector_search_blocked", reason="invalid_exclude_id")
            return []

    params: dict[str, Any] = {"threshold": threshold, "limit": limit}

    # Use CAST() instead of :: for all type casts — the asyncpg SQLAlchemy dialect
    # can misparse :name::type sequences (treating the second : as another param
    # prefix), leading to PostgresSyntaxError.  CAST() is unambiguous.
    user_filter = ""
    if user_id:
        params["user_id"] = user_id
        user_filter = "AND user_id = CAST(:user_id AS uuid)"

    archived_filter = "AND is_archived = false" if filter_archived else ""
    resolved_filter = "AND resolved = false" if table == "purchase_gaps" else ""

    exclude_filter = ""
    if exclude_id is not None:
        params["exclude_id"] = exclude_id
        exclude_filter = "AND id != CAST(:exclude_id AS uuid)"

    category_filter = ""
    if filter_category is not None:
        params["filter_category"] = filter_category
        category_filter = "AND category = :filter_category"

    # The vector literal is interpolated directly (not a bound param) because
    # asyncpg cannot bind custom pgvector types via $N params.  The value is
    # pre-validated by _VEC_RE above so interpolation is safe.
    sql = text(f"""
        SELECT *, 1 - (embedding <=> CAST('{vec}' AS vector)) AS similarity_score
        FROM {table}
        WHERE embedding IS NOT NULL
          {user_filter}
          {archived_filter}
          {exclude_filter}
          {category_filter}
          {resolved_filter}
          AND 1 - (embedding <=> CAST('{vec}' AS vector)) >= :threshold
        ORDER BY embedding <=> CAST('{vec}' AS vector)
        LIMIT :limit
    """)
    # Use a savepoint so that a DB-level failure (e.g. pgvector not installed,
    # embedding column missing) rolls back only this sub-operation and leaves
    # the outer SQLAlchemy session/transaction in a usable state.  Without this
    # the session enters InFailedSQLTransactionError and every subsequent query
    # in the same request fails — which is the root cause of the
    # "Could not generate today's outfit" error.
    try:
        async with session.begin_nested():
            result = await session.execute(sql, params)
            rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("pgvector_search_failed", table=table, error=str(exc))
        return []
