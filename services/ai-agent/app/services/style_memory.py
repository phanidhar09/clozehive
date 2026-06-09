"""Persistent per-user style memory for FANI.

The agent is otherwise stateless: conversation history is passed per-request and
forgotten afterward. This module gives FANI durable, cross-session memory of a
user's *style preferences* — short facts like "Dislikes the colour yellow" or
"Prefers smart-casual for work" — stored in the ``user_style_memory`` table
(pgvector) and retrieved on every chat.

Flow
────
- ``retrieve_style_memories``  — called before each chat; returns the most
  relevant remembered preferences to inject into the prompt.
- ``extract_and_store_memories`` — called *after* a reply (fire-and-forget, so
  chat latency is unaffected); uses a cheap LLM pass to pull durable preferences
  out of the user's message, then embeds + upserts them with de-duplication.

Everything degrades gracefully: any DB / OpenAI failure is logged and swallowed
so the chat path never breaks because memory was unavailable.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langsmith import traceable

from app.core.config import get_settings
from app.services.vector_store import embed_query, get_openai, get_pool

logger = structlog.get_logger("style_memory")
settings = get_settings()

# Valid `kind` values mirror the DB CHECK-free convention in migration 029.
_VALID_KINDS = {
    "color_pref",
    "style_pref",
    "fit_pref",
    "occasion",
    "dislike",
    "brand",
    "general",
}

_EXTRACTION_SYSTEM = """\
You extract DURABLE personal style preferences from a user's message to a fashion
stylist. Durable = a lasting fact about the user's taste, body, or habits that
would still be useful weeks from now.

INCLUDE: colour likes/dislikes, preferred styles/aesthetics, fit preferences,
fabrics, brands, body-shape notes, recurring occasions (e.g. "works in tech,
dresses smart-casual"), hard constraints ("never wears heels").

EXCLUDE: one-off requests ("what should I wear today?"), questions, weather,
trip-specific details, anything transient or already obvious.

Return ONLY valid JSON, no markdown:
{"memories": [{"content": "<short third-person fact>", "kind": "<one of: color_pref, style_pref, fit_pref, occasion, dislike, brand, general>"}]}

Rules:
- "content" is a concise, self-contained fact in neutral third-person voice
  (e.g. "Dislikes the colour yellow", "Prefers oversized fits").
- Output at most 3 memories. If nothing durable is present, return {"memories": []}.
- Never invent preferences the user did not express.
"""


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _enabled() -> bool:
    return (
        settings.style_memory_enabled
        and settings.vector_store == "pgvector"
        and bool(settings.openai_api_key)
    )


# ── Retrieval ─────────────────────────────────────────────────────────────────

@traceable(name="style_memory_retrieve", run_type="retriever")
async def retrieve_style_memories(user_id: str, query: str, limit: int | None = None) -> list[str]:
    """Return the user's most relevant remembered style preferences as strings.

    Uses vector similarity against the chat query when embeddings are available;
    falls back to most-recent memories so a user with no embedding-indexed rows
    (or an embedding failure) still gets their preferences.
    """
    if not user_id or not _enabled():
        return []

    limit = limit or settings.style_memory_retrieve_limit
    try:
        pool = await get_pool()
    except Exception as exc:
        logger.warning("style_memory_pool_unavailable", error=str(exc))
        return []

    try:
        embedding = await embed_query(query) if query.strip() else None
    except Exception as exc:
        logger.warning("style_memory_embed_failed", error=str(exc))
        embedding = None

    try:
        async with pool.acquire() as conn:
            if embedding is not None:
                rows = await conn.fetch(
                    """
                    SELECT content, 1 - (embedding <=> $2::vector) AS score
                    FROM user_style_memory
                    WHERE user_id = $1::uuid
                      AND embedding IS NOT NULL
                      AND 1 - (embedding <=> $2::vector) >= $3
                    ORDER BY embedding <=> $2::vector
                    LIMIT $4
                    """,
                    user_id,
                    _vector_literal(embedding),
                    settings.style_memory_score_threshold,
                    limit,
                )
                if rows:
                    return [r["content"] for r in rows]
            # Fallback: most-recent preferences (also covers rows without embeddings).
            rows = await conn.fetch(
                """
                SELECT content
                FROM user_style_memory
                WHERE user_id = $1::uuid
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
        return [r["content"] for r in rows]
    except Exception as exc:
        logger.warning("style_memory_retrieve_failed", error=str(exc))
        return []


# ── Extraction + storage ────────────────────────────────────────────────────

async def _extract_candidates(user_message: str) -> list[dict[str, str]]:
    """Ask a cheap model to pull durable preferences out of the user's message."""
    try:
        resp = await get_openai().chat.completions.create(
            model=settings.style_memory_extract_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM},
                {"role": "user", "content": user_message[:4000]},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("style_memory_extract_failed", error=str(exc))
        return []

    out: list[dict[str, str]] = []
    for item in (data.get("memories") or [])[:3]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content or len(content) > 280:
            continue
        kind = str(item.get("kind", "general")).strip().lower()
        if kind not in _VALID_KINDS:
            kind = "general"
        out.append({"content": content, "kind": kind})
    return out


@traceable(name="style_memory_extract_store")
async def extract_and_store_memories(user_id: str, user_message: str) -> int:
    """Extract durable preferences from a message and upsert them (dedup'd).

    Returns the number of new memories stored. Safe to call fire-and-forget — all
    failures are swallowed. Only the USER message is mined (never the assistant
    reply), so FANI's own suggestions are not mistaken for the user's tastes.
    """
    if not user_id or not _enabled() or not user_message.strip():
        return 0

    candidates = await _extract_candidates(user_message)
    if not candidates:
        return 0

    try:
        pool = await get_pool()
    except Exception as exc:
        logger.warning("style_memory_pool_unavailable", error=str(exc))
        return 0

    stored = 0
    for cand in candidates:
        content, kind = cand["content"], cand["kind"]
        try:
            embedding = await embed_query(content)
        except Exception as exc:
            logger.warning("style_memory_candidate_embed_failed", error=str(exc))
            embedding = None

        try:
            async with pool.acquire() as conn:
                # Dedup: skip exact text match or a near-duplicate by embedding.
                exact = await conn.fetchval(
                    "SELECT 1 FROM user_style_memory "
                    "WHERE user_id = $1::uuid AND lower(content) = lower($2) LIMIT 1",
                    user_id,
                    content,
                )
                if exact:
                    continue
                if embedding is not None:
                    dup = await conn.fetchval(
                        """
                        SELECT 1 FROM user_style_memory
                        WHERE user_id = $1::uuid
                          AND embedding IS NOT NULL
                          AND 1 - (embedding <=> $2::vector) >= $3
                        LIMIT 1
                        """,
                        user_id,
                        _vector_literal(embedding),
                        settings.style_memory_dedup_threshold,
                    )
                    if dup:
                        continue

                await conn.execute(
                    """
                    INSERT INTO user_style_memory (user_id, content, kind, source, embedding)
                    VALUES ($1::uuid, $2, $3, 'chat', $4::vector)
                    """,
                    user_id,
                    content,
                    kind,
                    _vector_literal(embedding) if embedding is not None else None,
                )
                stored += 1

                # Cap memory size: prune the oldest beyond the per-user limit.
                await conn.execute(
                    """
                    DELETE FROM user_style_memory
                    WHERE id IN (
                        SELECT id FROM user_style_memory
                        WHERE user_id = $1::uuid
                        ORDER BY created_at DESC
                        OFFSET $2
                    )
                    """,
                    user_id,
                    settings.style_memory_max_per_user,
                )
        except Exception as exc:
            logger.warning("style_memory_store_failed", error=str(exc))
            continue

    if stored:
        logger.info("style_memory_stored", user_id=user_id, count=stored)
    return stored


def format_memories_block(memories: list[str]) -> str:
    """Render retrieved memories as a prompt block, or '' when there are none."""
    if not memories:
        return ""
    lines = "\n".join(f"- {m}" for m in memories)
    return (
        "\n\n[What I remember about your style — apply these silently, and defer "
        "to anything the user says now if it conflicts]:\n" + lines
    )
