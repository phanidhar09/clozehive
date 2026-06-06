"""Postgres helpers for idempotent worker processing."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import get_settings

settings = get_settings()
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=8)
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def mark_processing(request_id: UUID) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE ai_requests SET status='processing', updated_at=NOW() WHERE id=$1",
        request_id,
    )


async def complete_request(request_id: UUID, result: dict[str, Any]) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE ai_requests
        SET status='completed', result_payload=$2::jsonb, updated_at=NOW()
        WHERE id=$1
        """,
        request_id,
        json.dumps(result, default=str),
    )


async def fail_request(request_id: UUID, error: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE ai_requests
        SET status='failed', error_message=$2, updated_at=NOW()
        WHERE id=$1
        """,
        request_id,
        error[:2000],
    )


async def request_age_seconds(request_id: UUID) -> float:
    """Age of an ai_request since creation (seconds)."""
    pool = await get_pool()
    age = await pool.fetchval(
        "SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) FROM ai_requests WHERE id=$1",
        request_id,
    )
    try:
        return float(age or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def already_processed(event_id: UUID) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT 1 FROM processed_events WHERE event_id=$1", event_id)
    return row is not None


async def record_processed(event_id: UUID, topic: str, request_id: UUID) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO processed_events (event_id, topic, request_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (event_id) DO NOTHING
        """,
        event_id,
        topic,
        request_id,
    )
