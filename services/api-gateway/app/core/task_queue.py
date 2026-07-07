"""ARQ task-queue producer.

The api-gateway stays synchronous-fast by handing heavy AI work (vision
analysis, outfit/packing generation) to the ai-worker over Redis. This module
owns a single shared ARQ Redis pool and the enqueue helper that:

  1. inserts an ``ai_requests`` row (status ``accepted``) for status polling, and
  2. enqueues the matching ARQ job with ``_job_id = request_id`` so the same
     request is never double-processed while in flight.

The worker side lives in ``services/ai-worker/app/worker.py``; the function
names below must match the task functions registered there.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("task_queue")
settings = get_settings()

# Task function names — must stay in sync with ai-worker/app/worker.py.
TASK_ANALYZE_IMAGE = "analyze_image_task"
TASK_GENERATE_OUTFIT = "generate_outfit_task"

_pool: ArqRedis | None = None


def should_offload_heavy_work() -> bool:
    """Whether heavy post-write work should go to the durable ARQ queue.

    Gated by HEAVY_WORK_ASYNC. When False (default) callers fall back to
    in-process FastAPI BackgroundTasks — no worker required.
    """
    return settings.heavy_work_async


async def get_arq_pool() -> ArqRedis:
    """Lazily create and cache the shared ARQ Redis pool."""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def enqueue_ai_job(
    session: AsyncSession,
    *,
    user_id: UUID,
    request_type: str,
    task_name: str,
    task_args: list[Any],
    input_payload: dict[str, Any] | None = None,
) -> UUID:
    """Record an ``ai_requests`` row and enqueue the matching ARQ job.

    Returns the ``request_id`` the caller hands back to the client for polling.
    The request_id doubles as the ARQ job_id, so enqueuing the same logical
    request twice while one is still in flight is a no-op.
    """
    request_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO ai_requests (id, user_id, request_type, status, input_payload)
            VALUES (:id, :user_id, :request_type, 'accepted', CAST(:input_payload AS jsonb))
            """
        ),
        {
            "id": request_id,
            "user_id": user_id,
            "request_type": request_type,
            "input_payload": json.dumps(input_payload or {}, default=str),
        },
    )
    await session.commit()

    pool = await get_arq_pool()
    job = await pool.enqueue_job(task_name, str(request_id), *task_args, _job_id=str(request_id))
    # job is None only if a job with this _job_id already exists — safe to ignore.
    logger.info(
        "ai_job_enqueued",
        request_id=str(request_id),
        request_type=request_type,
        task=task_name,
        deduped=job is None,
    )
    return request_id
