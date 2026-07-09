"""Closet item vector similarity helpers."""

from __future__ import annotations

import asyncio
from uuid import UUID

from langsmith import traceable
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.embedding_service import item_to_embedding_text
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.db.session import AsyncSessionLocal
from app.models.closet import ClosetItem

settings = get_settings()
logger = get_logger("similarity_service")

_emb_client: AsyncOpenAI | None = None


def _embedding_client() -> AsyncOpenAI:
    global _emb_client
    if _emb_client is None:
        _emb_client = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        )
    return _emb_client


@traceable(name="gateway_openai_embedding", run_type="embedding")
async def generate_item_embedding(item: ClosetItem) -> list[float]:
    """
    Generate a rich embedding for a saved ClosetItem.

    Uses the same item_to_embedding_text() function as pgvector search queries
    so stored vectors and query vectors are always in the same semantic space.
    Previously this used a thin 4-field concat (name + category + color + tags)
    which caused stored embeddings and search embeddings to differ, degrading
    cosine similarity results.
    """
    description = item_to_embedding_text(
        {
            "name": item.name,
            "category": item.category,
            "color": item.color or "",
            "fabric": item.fabric or "",
            "pattern": item.pattern or "",
            "season": item.season or [],
            "occasion": item.occasion or [],
            "tags": item.tags or [],
            "notes": item.notes or "",
            "brand": item.brand or "",
        }
    )
    if not settings.openai_api_key:
        logger.warning("embedding_fallback", reason="OPENAI_API_KEY not set", item_id=str(item.id))
        return [0.0] * 1536
    response = await _embedding_client().embeddings.create(
        model=settings.embedding_model,
        input=description,
        timeout=20.0,
    )
    vector = response.data[0].embedding
    # text-embedding-3-small and ada-002 both produce 1536 dims by default
    if len(vector) != 1536:
        raise ValueError(f"Embedding model returned {len(vector)} dimensions; expected 1536")
    return [float(v) for v in vector]


async def find_similar_items(session: AsyncSession, item_id: str, user_id: str, limit: int = 5) -> list[ClosetItem]:
    source = await session.get(ClosetItem, UUID(item_id))
    if source is None or source.user_id != UUID(user_id) or not source.embedding:
        return []
    result = await session.execute(
        select(ClosetItem)
        .where(
            ClosetItem.user_id == UUID(user_id),
            ClosetItem.id != UUID(item_id),
            ClosetItem.embedding.is_not(None),
        )
        .order_by(ClosetItem.embedding.cosine_distance(source.embedding))
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_item_embedding_in_request(session: AsyncSession, item_id: str) -> None:
    """
    Recompute embedding inside the current request transaction.

    Call from route handlers that still hold the dependency-injected session;
    uses ``flush`` only — :func:`get_session` commits at the end of the request.
    """
    item = await session.get(ClosetItem, UUID(item_id))
    if item is None:
        return
    item.embedding = await generate_item_embedding(item)
    await session.flush()


async def update_item_embedding_job(item_id: str) -> None:
    """
    Background-safe embedding update: opens its own session and commits.

    Use from FastAPI ``BackgroundTasks`` or fire-and-forget asyncio tasks so
    work is not tied to the request session lifecycle.

    Call sites MUST commit the row before scheduling this in-process — the job
    runs before dependency teardown, so an uncommitted row is invisible here.
    The retry below only papers over the durable-queue (ARQ) variant of that
    race, where the worker may pick the job up moments before the commit lands.
    """
    for attempt in range(3):
        async with AsyncSessionLocal() as session:
            try:
                # Bound the row-lock wait: if the row is still locked by an
                # uncommitted request transaction, fail loudly instead of
                # hanging forever (the failure shows up in background-task logs).
                await session.execute(text("SET LOCAL lock_timeout = '5s'"))
                item = await session.get(ClosetItem, UUID(item_id))
                if item is not None:
                    item.embedding = await generate_item_embedding(item)
                    await session.commit()
                    return
            except Exception:
                await session.rollback()
                raise
        # Row not visible yet — likely racing the creating transaction's commit.
        await asyncio.sleep(0.5 * (attempt + 1))
    logger.warning("embedding_job_item_missing", item_id=item_id)


async def schedule_embedding_update(background_tasks, item_id: str) -> None:
    """Schedule an item embedding refresh, off the request path.

    Two transports, selected by ``settings.heavy_work_async``:

    * **arq** (True) — enqueue to the durable ``clozehive-worker`` queue so the
      web dyno never spends CPU/DB time on embeddings. If the queue is
      unreachable we fall back to the in-process task rather than drop the work.
    * **inprocess** (False, default) — run as a FastAPI BackgroundTask in this
      process after the response is sent (single-dyno behaviour, unchanged).

    Either way the API response returns immediately.
    """
    from app.core.metrics import record_embedding_job

    if settings.heavy_work_async:
        from app.core.task_queue import enqueue_job

        if await enqueue_job("refresh_item_embedding", item_id):
            record_embedding_job("arq")
            return
        logger.warning("embedding_enqueue_fell_back_inprocess", item_id=item_id)

    record_embedding_job("inprocess")
    background_tasks.add_task(update_item_embedding_job, item_id)
