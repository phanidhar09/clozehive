"""Account-deletion saga — durable cross-service data purge via a transactional outbox.

When a user deletes their account, their wardrobe data lives in a separate
database (closet-service). A best-effort inline HTTP call can fail (network blip,
closet-service restarting) and leave that data orphaned. This module makes the
purge durable:

  1. ``record_purge`` writes a ``purge_outbox`` row in the SAME transaction as the
     user deletion (transactional outbox) — the intent can never be lost.
  2. ``run_purge`` attempts the downstream purge and updates the row.
  3. ``reconcile_pending`` (run on a background loop) retries pending rows with
     backoff until they succeed or exhaust ``MAX_ATTEMPTS`` (then ``failed`` +
     an alert metric for manual intervention).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.purge_outbox import PurgeOutbox

logger = get_logger("account_purge")
settings = get_settings()

TARGET_CLOSET = "closet_service"
MAX_ATTEMPTS = 10
# Don't retry a row more often than this (seconds) — paired with the loop interval.
_RECONCILE_INTERVAL = 60


async def record_purge(session, user_id: UUID, target: str = TARGET_CLOSET) -> None:
    """Insert a pending outbox row. Call within the deletion transaction so the
    intent commits atomically with the user removal."""
    session.add(PurgeOutbox(user_id=user_id, target=target, status="pending"))


async def _attempt_closet_purge(user_id: str) -> tuple[bool, str]:
    """Single HTTP attempt to purge the user's closet-service data.

    Returns (ok, detail). ok=True only on a 2xx (or a 404 = already gone).
    """
    base = (settings.closet_service_url or "").rstrip("/")
    if not base:
        return True, "closet_service_url unset — nothing to purge"
    if not settings.internal_service_token:
        return False, "INTERNAL_SERVICE_TOKEN unset"
    url = f"{base}/internal/users/{user_id}"
    headers = {"X-Internal-Token": settings.internal_service_token}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(url, headers=headers)
        if resp.status_code in (200, 204, 404):
            return True, f"status={resp.status_code}"
        return False, f"status={resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


async def run_purge_for_user(user_id: str) -> bool:
    """Attempt the purge once and update the matching pending outbox row.

    Used for the inline attempt right after deletion. Returns True on success.
    """
    ok, detail = await _attempt_closet_purge(user_id)
    async with AsyncSessionLocal() as session:
        if ok:
            await session.execute(
                update(PurgeOutbox)
                .where(PurgeOutbox.user_id == UUID(user_id), PurgeOutbox.status == "pending")
                .values(status="done", last_error=None)
            )
        else:
            await session.execute(
                update(PurgeOutbox)
                .where(PurgeOutbox.user_id == UUID(user_id), PurgeOutbox.status == "pending")
                .values(attempts=PurgeOutbox.attempts + 1, last_error=detail[:500])
            )
        await session.commit()
    if ok:
        logger.info("closet_data_purged", user_id=user_id, detail=detail)
    else:
        logger.warning("closet_purge_attempt_failed", user_id=user_id, detail=detail)
    return ok


async def reconcile_pending() -> None:
    """One reconciliation pass: retry every pending outbox row, mark terminal."""
    async with AsyncSessionLocal() as session:
        rows = (
            (await session.execute(select(PurgeOutbox).where(PurgeOutbox.status == "pending").limit(100)))
            .scalars()
            .all()
        )

    for row in rows:
        ok, detail = await _attempt_closet_purge(str(row.user_id))
        async with AsyncSessionLocal() as session:
            if ok:
                values: dict[str, Any] = {"status": "done", "last_error": None}
            else:
                attempts = row.attempts + 1
                status = "failed" if attempts >= MAX_ATTEMPTS else "pending"
                values = {"status": status, "attempts": attempts, "last_error": detail[:500]}
                if status == "failed":
                    logger.error("closet_purge_giving_up", user_id=str(row.user_id), attempts=attempts)
                    _alert_failed(str(row.user_id))
            await session.execute(update(PurgeOutbox).where(PurgeOutbox.id == row.id).values(**values))
            await session.commit()


def _alert_failed(user_id: str) -> None:
    """Surface an unrecoverable purge for manual intervention (metric + Sentry)."""
    try:
        from app.core.metrics import record_purge_failed

        record_purge_failed()
    except Exception:
        pass


async def reconcile_loop() -> None:
    """Background loop — started in the app lifespan. Survives restarts because
    the outbox is in Postgres: pending rows are picked up on the next boot."""
    while True:
        try:
            await reconcile_pending()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("purge_reconcile_error", error=str(exc))
        await asyncio.sleep(_RECONCILE_INTERVAL)
