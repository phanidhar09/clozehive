"""
Redis cache service — typed helpers with automatic TTL and JSON serialisation.
Gracefully degrades (logs warning, returns None) when Redis is unavailable.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

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


async def set(key: str, value: Any, ttl: int) -> None:
    try:
        client = await get_redis()
        await client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("cache_set_error", key=key, error=str(exc))


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

def user_profile_key(user_id: str) -> str:
    return namespaced_key("profile", user_id)


def closet_key(user_id: str) -> str:
    return namespaced_key("closet", user_id)


def weather_key(destination: str, start: str, end: str) -> str:
    return namespaced_key("weather", destination.lower(), start, end)


def social_key(user_id: str, kind: str) -> str:
    return namespaced_key("social", kind, user_id)


def websocket_user_channel(user_id: str) -> str:
    return namespaced_key("ws", "user", user_id)


def websocket_broadcast_channel() -> str:
    return namespaced_key("ws", "broadcast")
