"""Shared embedding service used by all RAG features.

Provides:
- generate_text_embedding(text)  — OpenAI text-embedding-3-small (1536-dim)
- item_to_embedding_text(item)   — normalise closet item metadata to searchable text
- cosine_search(session, model, limit, threshold, vector)  — generic pgvector search
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid as _uuid
from collections import OrderedDict
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


_EMBED_CHAR_LIMIT = 8000  # text-embedding-3-small token limit ≈ 8191 tokens; 8000 chars is a safe proxy

# ── Embedding cache ───────────────────────────────────────────────────────────
# Two tiers: an in-process LRU (free, per-worker) and Redis (cross-worker).
# Chat and RAG paths frequently embed identical text (same message embedded for
# closet search, memory retrieval, and history search) — caching removes the
# repeated OpenAI round-trips entirely.

_EMBED_CACHE_MAX = 512
_EMBED_CACHE_TTL = 21_600  # 6h — embeddings for fixed model/text never go stale
_embed_lru: OrderedDict[str, list[float]] = OrderedDict()


def _embed_cache_key(text_value: str) -> str:
    digest = hashlib.sha256(text_value.encode("utf-8")).hexdigest()[:32]
    return f"embed:{settings.embedding_model}:{digest}"


def _lru_get(key: str) -> list[float] | None:
    vec = _embed_lru.get(key)
    if vec is not None:
        _embed_lru.move_to_end(key)
    return vec


def _lru_put(key: str, vec: list[float]) -> None:
    _embed_lru[key] = vec
    _embed_lru.move_to_end(key)
    while len(_embed_lru) > _EMBED_CACHE_MAX:
        _embed_lru.popitem(last=False)


async def _redis_cache_get(key: str) -> list[float] | None:
    try:
        from app.core.redis import get_redis  # lazy: redis is optional at import time

        redis = await get_redis()
        raw = await redis.get(key)
        if raw:
            vec = json.loads(raw)
            if isinstance(vec, list) and len(vec) == _EMBEDDING_DIM:
                return vec
    except Exception:
        pass
    return None


async def _redis_cache_set(key: str, vec: list[float]) -> None:
    try:
        from app.core.redis import get_redis

        redis = await get_redis()
        await redis.set(key, json.dumps(vec), ex=_EMBED_CACHE_TTL)
    except Exception:
        pass


@traceable(name="rag_embed_text", run_type="embedding")
async def generate_text_embedding(text_input: str) -> list[float] | None:
    """Return a 1536-dim embedding or None when OpenAI is unavailable.

    Results are cached (in-process LRU + Redis) keyed on the model + text hash,
    so repeated queries cost no API calls.
    """
    if not settings.openai_api_key:
        return None
    stripped = text_input.strip()
    if not stripped:
        return None
    if len(stripped) > _EMBED_CHAR_LIMIT:
        logger.warning(
            "embedding_text_truncated",
            original_len=len(stripped),
            truncated_to=_EMBED_CHAR_LIMIT,
        )
        stripped = stripped[:_EMBED_CHAR_LIMIT]

    cache_key = _embed_cache_key(stripped)
    cached = _lru_get(cache_key)
    if cached is not None:
        return cached
    cached = await _redis_cache_get(cache_key)
    if cached is not None:
        _lru_put(cache_key, cached)
        return cached

    try:
        response = await _get_client().embeddings.create(
            model=settings.embedding_model,
            input=stripped,
        )
        embedding = response.data[0].embedding
        _lru_put(cache_key, embedding)
        await _redis_cache_set(cache_key, embedding)
        return embedding
    except Exception as exc:
        logger.warning("embedding_failed", error=str(exc))
        return None


def _resolve(item: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string value among the given key aliases."""
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            return str(v[0]).strip()
    return ""


def _resolve_list(item: dict[str, Any], *keys: str) -> list[str]:
    """Return first non-empty list found among the given key aliases."""
    for k in keys:
        v = item.get(k)
        if isinstance(v, list) and v:
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
    return []


def item_to_embedding_text(item: dict[str, Any]) -> str:
    """
    Convert closet item metadata into a rich, semantically dense string for embedding.

    Handles both DB-column names (color, fabric, occasion, season, tags, notes)
    AND vision-analysis field names (primary_color, material, occasion_tags,
    season_tags, style_tags, description, subcategory, fit) so the same function
    works for stored items *and* freshly-analysed items that haven't been saved yet.

    Key design choices:
    - Lead with the most discriminating fields (category + name + color + material)
    - Repeat category and color at the end — embedding models benefit from emphasis
    - Use natural-language phrasing ("A navy blue slim-fit chino pant…") rather
      than "Key: Value" format — better semantic neighbourhood clustering
    - Include all available metadata so semantically similar items end up close
      in vector space regardless of which fields are populated
    """
    # ── Field resolution (handles both naming conventions) ───────────────────
    category    = _resolve(item, "category")
    subcategory = _resolve(item, "subcategory")
    name        = _resolve(item, "name")
    color       = _resolve(item, "color", "primary_color")
    material    = _resolve(item, "fabric", "material")
    pattern     = _resolve(item, "pattern")
    fit         = _resolve(item, "fit")
    brand       = _resolve(item, "brand")
    description = _resolve(item, "notes", "description")

    occasions   = _resolve_list(item, "occasion", "occasion_tags")
    seasons     = _resolve_list(item, "season", "season_tags")
    tags        = _resolve_list(item, "tags", "style_tags")
    sec_colors  = _resolve_list(item, "secondary_colors")

    # ── Build natural-language sentence ──────────────────────────────────────
    # Format: "<color> <material> <fit> <subcategory or category> called '<name>'"
    item_type = subcategory or category
    descriptor_parts = [p for p in [color, material, fit, item_type] if p]
    headline = " ".join(descriptor_parts)
    if name and name.lower() != item_type.lower():
        headline = f"{headline} called '{name}'"

    parts: list[str] = [headline] if headline.strip() else []

    if description:
        parts.append(description)

    if brand:
        parts.append(f"Brand: {brand}")

    if pattern and pattern.lower() not in ("solid", "unknown", ""):
        parts.append(f"Pattern: {pattern}")

    if seasons:
        parts.append(f"Suitable for {', '.join(seasons)}")

    if occasions:
        parts.append(f"Worn for {', '.join(occasions)}")

    if tags:
        parts.append(f"Style: {', '.join(tags)}")

    if sec_colors:
        parts.append(f"Also features {', '.join(sec_colors)}")

    # ── Repeat key discriminators at the end for embedding emphasis ──────────
    # Embedding models weight earlier tokens more; repeating the most important
    # attributes at the end improves retrieval precision significantly.
    tail: list[str] = []
    if category:
        tail.append(category)
    if color:
        tail.append(color)
    if material:
        tail.append(material)
    if tail:
        parts.append(" · ".join(tail))

    return ". ".join(p for p in parts if p.strip()) + "."


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
        # Drop the raw vector (1536 floats per row) — no caller uses it, and it
        # otherwise bloats every payload built from these rows.
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d.pop("embedding", None)
            out.append(d)
        return out
    except Exception as exc:
        logger.warning("pgvector_search_failed", table=table, error=str(exc))
        return []
