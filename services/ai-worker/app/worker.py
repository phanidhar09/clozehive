"""ARQ worker for asynchronous AI workflows.

Replaces the previous Kafka/Redpanda consumer with an ARQ task queue backed by
the Redis the rest of the stack already runs. The api-gateway enqueues jobs
(see ``app/core/task_queue.py`` there); each task function below mirrors one of
the old Kafka command topics.

Run with::

    arq app.worker.WorkerSettings

Job lifecycle is tracked in the ``ai_requests`` table (status:
accepted → processing → completed | failed) so the gateway can poll for results.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.services import ai_agent_client, db

settings = get_settings()
logger = get_logger("ai_worker")


# ── Task functions ──────────────────────────────────────────────────────────
#
# Every task takes the ARQ ``ctx`` first, then the request_id (which is also the
# ARQ job_id, so enqueuing the same request twice is a no-op while in flight).
# On success we persist the result; on the final retry we record the failure.

async def _fail_on_last_try(ctx: dict[str, Any], request_id: UUID, exc: Exception) -> None:
    """Record a failed status only once ARQ has exhausted its retries."""
    if ctx.get("job_try", 1) >= settings.max_attempts:
        await db.fail_request(request_id, str(exc))


async def analyze_image_task(
    ctx: dict[str, Any],
    request_id: str,
    file_path: str,
    media_type: str = "image/jpeg",
) -> dict[str, Any]:
    rid = UUID(request_id)
    logger.info("analyze_image_started", request_id=request_id, attempt=ctx.get("job_try"))
    await db.mark_processing(rid)
    try:
        analysis = await ai_agent_client.analyze_image(file_path, media_type)
        payload = {"analysis": analysis}
        await db.complete_request(rid, payload)
        logger.info("analyze_image_completed", request_id=request_id)
        return payload
    except Exception as exc:  # noqa: BLE001 — re-raised below for ARQ retry
        logger.error("analyze_image_failed", request_id=request_id, error=str(exc))
        await _fail_on_last_try(ctx, rid, exc)
        raise


async def generate_outfit_task(
    ctx: dict[str, Any],
    request_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    rid = UUID(request_id)
    logger.info("generate_outfit_started", request_id=request_id, attempt=ctx.get("job_try"))
    await db.mark_processing(rid)
    try:
        result = await ai_agent_client.generate_outfit(payload)
        await db.complete_request(rid, result)
        logger.info("generate_outfit_completed", request_id=request_id)
        return result
    except Exception as exc:  # noqa: BLE001 — re-raised below for ARQ retry
        logger.error("generate_outfit_failed", request_id=request_id, error=str(exc))
        await _fail_on_last_try(ctx, rid, exc)
        raise


async def generate_packing_task(
    ctx: dict[str, Any],
    request_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    rid = UUID(request_id)
    logger.info("generate_packing_started", request_id=request_id, attempt=ctx.get("job_try"))
    await db.mark_processing(rid)
    try:
        result = await ai_agent_client.generate_packing(payload)
        await db.complete_request(rid, result)
        logger.info("generate_packing_completed", request_id=request_id)
        return result
    except Exception as exc:  # noqa: BLE001 — re-raised below for ARQ retry
        logger.error("generate_packing_failed", request_id=request_id, error=str(exc))
        await _fail_on_last_try(ctx, rid, exc)
        raise


# ── Worker lifecycle ────────────────────────────────────────────────────────

async def on_startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    await db.get_pool()  # warm the asyncpg pool
    logger.info("ai_worker_starting", redis=settings.redis_url)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ai_agent_client.close()
    await db.close()
    logger.info("ai_worker_stopped")


class WorkerSettings:
    """ARQ entrypoint: ``arq app.worker.WorkerSettings``."""

    functions = [analyze_image_task, generate_outfit_task, generate_packing_task]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_tries = settings.max_attempts
    # Keep finished job results in Redis briefly so the gateway can also read
    # them straight from ARQ if it wants to; the DB row is the source of truth.
    keep_result = 3600
