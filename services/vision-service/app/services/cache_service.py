"""
Redis cache service — typed helpers with automatic TTL and JSON serialisation.
Gracefully degrades (logs warning, returns None) when Redis is unavailable.
"""

from __future__ import annotations

import builtins
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("cache")
settings = get_settings()

_redis: aioredis.Redis | None = None
_KEY_PREFIX = "clozehive:v1"


def namespaced_key(*parts: str) -> str:
    """Build a stable Redis key namespace shared across gateway instances."""
    safe_parts = [str(part).strip().replace(" ", "_") for part in parts if str(part).strip()]
    return ":".join([_KEY_PREFIX, *safe_parts])


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis


async def get(key: str) -> Any | None:
    try:
        client = await get_redis()
        value = await client.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as exc:
        logger.warning("cache_get_error", key=key, error=str(exc))
        return None


async def set(key: str, value: Any, ttl: int) -> bool:
    try:
        client = await get_redis()
        ok = await client.setex(key, ttl, json.dumps(value, default=str))
        return bool(ok)
    except Exception as exc:
        logger.warning("cache_set_error", key=key, error=str(exc))
        return False


async def delete(key: str) -> None:
    try:
        client = await get_redis()
        await client.delete(key)
    except Exception as exc:
        logger.warning("cache_delete_error", key=key, error=str(exc))


async def delete_pattern(pattern: str) -> None:
    """Delete keys matching a glob pattern without blocking Redis with KEYS."""
    try:
        client = await get_redis()
        batch: list[str] = []
        async for key in scan_iter(pattern):
            batch.append(key)
            if len(batch) >= 500:
                await client.delete(*batch)
                batch.clear()
        if batch:
            await client.delete(*batch)
    except Exception as exc:
        logger.warning("cache_delete_pattern_error", pattern=pattern, error=str(exc))


async def scan_iter(pattern: str, count: int = 500) -> AsyncIterator[str]:
    """Yield matching keys using SCAN so cache invalidation scales safely."""
    client = await get_redis()
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=count)
        for key in keys:
            yield key
        if cursor == 0:
            break


async def ping() -> bool:
    try:
        client = await get_redis()
        return await client.ping()
    except Exception:
        return False


async def close() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# ── Named key helpers ─────────────────────────────────────────────────────────

def closet_key(user_id: str) -> str:
    return namespaced_key("closet", user_id)


def websocket_user_channel(user_id: str) -> str:
    """Per-user WS channel — must match the api-gateway hub's subscription."""
    return namespaced_key("ws", "user", user_id)


async def publish_ws(user_id: str, data: dict[str, Any]) -> None:
    """Best-effort real-time push to a user's browser tabs.

    Publishes to the channel the api-gateway WebSocket hub subscribes to
    (``clozehive:v1:ws:user:<id>``). Redis Pub/Sub is instance-wide (not scoped
    by DB index), so this reaches the hub even though vision-service uses a
    different Redis DB index. Never raises.
    """
    try:
        client = await get_redis()
        await client.publish(websocket_user_channel(user_id), json.dumps(data, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.debug("ws_publish_failed", user_id=user_id, error=str(exc))


async def invalidate_closet_list_cache(user_id: str) -> None:
    """Delete every cached closet-list page for a user."""
    await delete_pattern(f"{closet_key(user_id)}:*")
    await delete(closet_key(user_id))


async def invalidate_user_ai_cache(redis: aioredis.Redis, user_id: str) -> int:
    pattern = f"ai_cache:{user_id}:*"
    deleted = 0
    async for key in redis.scan_iter(match=pattern, count=100):
        deleted += await redis.delete(key)
    return deleted
