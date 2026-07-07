"""Semantic response cache for the gated FANI chat paths.

The exact-key AI cache (``cache_service.build_cache_key``) only hits when the
message text is byte-identical. Real traffic repeats *meaning*, not bytes:
"what should I wear today?" / "What do I wear today" / "outfit for today pls".
This cache stores recent grounded responses per user alongside the RAG query
embedding (already computed for pgvector retrieval — a lookup costs no extra
embedding call) and serves them back when a new turn's embedding is
near-identical (cosine ≥ threshold).

Safety properties — a hit is only possible when it cannot be wrong:

- **Scoped per user** — entries live under the user's own Redis key.
- **Closet/profile/weather pinned** — the entry stores ``closet_hash``,
  ``profile_hash`` and the weather condition; any change invalidates the match
  (an edited closet or different forecast must re-generate).
- **Only clean responses are stored** — the callers gate on: no validation
  errors, nothing removed by the grounding gate, no claim-audit violations,
  no images, shallow history. A response that needed correcting is never
  replayed.
- **TTL-bounded** — the whole per-user entry list expires together.

The list is small (``semantic_cache_max_entries``), so lookup is a linear scan
with a numpy dot product — microseconds, no vector index needed.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.core import cache_service
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("semantic_cache")
settings = get_settings()

_KEY_PREFIX = "semcache:v1:"


def _key(user_id: str) -> str:
    return f"{_KEY_PREFIX}{user_id}"


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def is_enabled() -> bool:
    return bool(settings.semantic_cache_enabled)


async def lookup(
    user_id: str,
    embedding: list[float] | None,
    *,
    closet_hash: str,
    profile_hash: str,
    weather_key: str = "",
) -> dict[str, Any] | None:
    """Return a cached response for a semantically equivalent prior turn.

    ``None`` on miss, disabled cache, or missing embedding. Never raises —
    a cache failure must not break chat.
    """
    if not is_enabled() or not embedding:
        return None
    try:
        entries = await cache_service.get(_key(user_id)) or []
        best: dict[str, Any] | None = None
        best_sim = 0.0
        for entry in entries:
            if (
                entry.get("closet_hash") != closet_hash
                or entry.get("profile_hash") != profile_hash
                or entry.get("weather_key", "") != weather_key
            ):
                continue
            sim = _cosine(embedding, entry.get("embedding") or [])
            if sim > best_sim:
                best_sim = sim
                best = entry
        if best is not None and best_sim >= float(settings.semantic_cache_threshold):
            logger.info(
                "semantic_cache_hit",
                user_id=user_id,
                similarity=round(best_sim, 4),
                age_s=int(time.time() - float(best.get("ts") or 0)),
            )
            return dict(best.get("response") or {})
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_cache_lookup_failed", error=str(exc))
        return None


async def store(
    user_id: str,
    embedding: list[float] | None,
    response: dict[str, Any],
    *,
    closet_hash: str,
    profile_hash: str,
    weather_key: str = "",
) -> None:
    """Store a clean, grounded response for future semantic hits.

    Callers are responsible for the cleanliness gate (no validation errors, no
    removed items, no claim violations, no images, shallow history) — this
    function only handles storage. Never raises.
    """
    if not is_enabled() or not embedding or not response:
        return
    try:
        key = _key(user_id)
        entries = await cache_service.get(key) or []
        entries.insert(
            0,
            {
                "embedding": list(embedding),
                "closet_hash": closet_hash,
                "profile_hash": profile_hash,
                "weather_key": weather_key,
                "response": response,
                "ts": time.time(),
            },
        )
        del entries[int(settings.semantic_cache_max_entries) :]
        await cache_service.set(key, entries, int(settings.semantic_cache_ttl))
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_cache_store_failed", error=str(exc))


async def invalidate(user_id: str) -> None:
    """Drop all semantic entries for a user (e.g. after a bulk closet import)."""
    try:
        await cache_service.delete(_key(user_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_cache_invalidate_failed", error=str(exc))
