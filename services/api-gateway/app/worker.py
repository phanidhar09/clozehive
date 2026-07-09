"""ARQ background worker for the API gateway.

Run as a separate Render service (``clozehive-worker``):

    arq app.worker.WorkerSettings

It consumes latency-insensitive heavy jobs that the web process enqueues via
:mod:`app.core.task_queue` when ``HEAVY_WORK_ASYNC=true``. Today that is the
closet embedding refresh; add new task coroutines to ``functions`` below as more
work is moved off the request path.

Deliberately NOT offloaded: background removal. It runs inside the live vision
SSE stream (``vision_pipeline.py`` emits ``item_ready`` events as each garment's
background finishes), so the user is actively watching — a durable queue would
add round-trips and break the real-time UX. Keep it in-process.

The worker shares the gateway's DB engine/session factory, so it must run the
same image with the same ``DATABASE_URL``. It does NOT run migrations (the web
service owns those); ``RUN_MIGRATIONS_ON_STARTUP`` must be false here.
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from app.api.v1.wardrobe.services.similarity_service import update_item_embedding_job
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import disconnect as db_disconnect

settings = get_settings()
logger = get_logger("worker")


async def refresh_item_embedding(ctx: dict[str, Any], item_id: str) -> None:
    """ARQ task: (re)generate a closet item's vector embedding.

    Thin wrapper over the shared, background-safe job so the in-process and
    durable paths run identical logic (own session + commit + visibility retry).
    """
    await update_item_embedding_job(item_id)


async def on_startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    logger.info("worker_startup", environment=settings.environment)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    # Dispose the DB engine's pool so connections are returned cleanly.
    await db_disconnect()
    logger.info("worker_shutdown")


class WorkerSettings:
    """ARQ entrypoint. ``arq app.worker.WorkerSettings`` reads these attrs."""

    functions = [refresh_item_embedding]
    redis_settings = RedisSettings.from_dsn(settings.effective_redis_state_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    # Bounded concurrency so a burst of uploads can't exhaust the DB pool or the
    # embedding API rate limit. Tune alongside db_pool_size / provider limits.
    max_jobs = 10
    # Embedding calls are fast; cap so a hung provider call can't wedge a slot.
    job_timeout = 60  # seconds
    # Retry transient failures (provider/DB blips) a couple of times.
    max_tries = 3
    # Don't retain results — these jobs are fire-and-forget side effects.
    keep_result = 0
