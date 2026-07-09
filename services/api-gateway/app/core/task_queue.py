"""ARQ job-queue client (enqueue side).

The web process uses this to hand latency-insensitive heavy work (currently the
closet embedding refresh) to the ``clozehive-worker`` ARQ service instead of
running it in-process. The worker side lives in :mod:`app.worker`.

Design
------
* One lazily-created, shared :class:`arq.connections.ArqRedis` pool per process,
  guarded by an ``asyncio.Lock`` so concurrent first-callers don't race.
* The queue lives on the **state** Redis (``effective_redis_state_url``), which
  is provisioned ``noeviction`` — a job must never be evicted under memory
  pressure the way an ``allkeys-lru`` cache entry can be.
* Enqueue is only reached when ``settings.heavy_work_async`` is True; when it is
  False this module is never imported on the hot path.

The pool is closed in the FastAPI lifespan shutdown (see ``app/main.py``).
"""

from __future__ import annotations

import asyncio
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("task_queue")
settings = get_settings()

_pool: ArqRedis | None = None
_pool_lock = asyncio.Lock()


def _redis_settings() -> RedisSettings:
    """Build ARQ RedisSettings from the (noeviction) state Redis URL."""
    return RedisSettings.from_dsn(settings.effective_redis_state_url)


async def get_arq_pool() -> ArqRedis:
    """Return the process-wide ARQ pool, creating it on first use."""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:  # re-check inside the lock
                _pool = await create_pool(_redis_settings())
                logger.info("arq_pool_created")
    return _pool


async def enqueue_job(function: str, *args: Any, **kwargs: Any) -> bool:
    """Enqueue an ARQ job by function name.

    Returns True if the job was accepted by Redis, False otherwise. Never raises
    — callers treat a False return as "fall back to running in-process" so a
    transient queue outage degrades gracefully instead of dropping the work.
    """
    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job(function, *args, **kwargs)
        if job is None:
            # enqueue_job returns None when a job with the same _job_id already
            # exists (dedupe). That's a successful no-op, not a failure.
            logger.debug("arq_job_deduped", function=function)
            return True
        logger.debug("arq_job_enqueued", function=function, job_id=job.job_id)
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort; caller falls back
        logger.warning("arq_enqueue_failed", function=function, error=str(exc))
        return False


async def close_arq_pool() -> None:
    """Close the ARQ pool on shutdown. Safe to call when it was never created."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("arq_pool_closed")
