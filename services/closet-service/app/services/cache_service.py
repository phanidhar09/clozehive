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
            socket_connect_timeout=10,
            socket_timeout=10,
            retry_on_timeout=True,
            health_check_interval=30,
            # Cap pool to 5 connections — Render Valkey free tier allows ~20 total
            # and we share those across cache ops + pubsub + vision service.
            max_connections=5,
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
    """
    Set a JSON value with TTL.

    Returns True if Redis acknowledged the write, False if Redis failed or rejected.
    Callers can use the return value for flows that cannot proceed without caching
    (e.g. OAuth CSRF state).
    """
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

def user_profile_key(user_id: str) -> str:
    return namespaced_key("profile", user_id)


def closet_key(user_id: str) -> str:
    return namespaced_key("closet", user_id)


# ── Closet list cache key helpers ─────────────────────────────────────────────

def _normalize_filter_value(value: Any) -> Any:
    """Recursively normalise a single filter value to a stable, JSON-serialisable form."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        return {
            str(k): _normalize_filter_value(v)
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            if _normalize_filter_value(v) is not None
        }
    if isinstance(value, (list, tuple, builtins.set)):
        normalized_items = [_normalize_filter_value(item) for item in value]
        normalized_items = [item for item in normalized_items if item is not None]
        try:
            return sorted(
                normalized_items,
                key=lambda item: json.dumps(item, sort_keys=True, default=str),
            )
        except TypeError:
            return normalized_items
    return str(value)


def normalize_closet_filters(filters: dict) -> dict:
    """Return a stable, sorted dict of non-None filter values ready for hashing."""
    normalized: dict[str, Any] = {}
    for key, value in filters.items():
        normalized_value = _normalize_filter_value(value)
        if normalized_value is not None:
            normalized[str(key)] = normalized_value
    return dict(sorted(normalized.items()))


def build_closet_cache_key(user_id: str, filters: dict) -> str:
    """Build a per-user, per-filter-combination Redis key for the closet list.

    Key format: ``clozehive:v1:closet:{user_id}:{sha256[:16]}``

    The hash is derived from the normalised filter dict so that semantically
    identical filter sets (e.g. different key ordering, whitespace in strings)
    always map to the same key.
    """
    normalized_filters = normalize_closet_filters(filters)
    payload = json.dumps(
        normalized_filters,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{closet_key(user_id)}:{digest}"


async def invalidate_closet_list_cache(user_id: str) -> None:
    """Delete every cached closet-list page for a user across all filter combinations.

    Covers both the new keyed format ``closet_key(user_id):{hash}`` and the
    legacy unkeyed format ``closet_key(user_id)`` so deployments that straddle
    both code versions don't serve stale data.
    """
    await delete_pattern(f"{closet_key(user_id)}:*")
    await delete(closet_key(user_id))


def weather_key(destination: str, start: str, end: str) -> str:
    return namespaced_key("weather", destination.lower(), start, end)


def social_key(user_id: str, kind: str) -> str:
    return namespaced_key("social", kind, user_id)


def websocket_user_channel(user_id: str) -> str:
    return namespaced_key("ws", "user", user_id)


def websocket_broadcast_channel() -> str:
    return namespaced_key("ws", "broadcast")


async def publish_ws(user_id: str, data: dict[str, Any]) -> None:
    """Best-effort real-time push to a user's browser tabs.

    Publishes to the same Redis channel the api-gateway WebSocket hub subscribes
    to (``clozehive:v1:ws:user:<id>``). Pub/Sub is instance-wide (not scoped by
    DB index), so this reaches the hub even though services use different Redis
    DB indexes. Never raises — a failed push must not break the request.
    """
    try:
        client = await get_redis()
        await client.publish(websocket_user_channel(user_id), json.dumps(data, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.debug("ws_publish_failed", user_id=user_id, error=str(exc))


# ── AI response cache helpers ─────────────────────────────────────────────────

def build_closet_hash(closet_items: list[dict[str, Any]]) -> str:
    ids = sorted(str(item.get("id", "")) for item in closet_items)
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_profile_hash(profile: dict | None) -> str:
    """Stable hash of style profile fields that affect AI responses."""
    if not profile:
        return ""
    fields = {
        "style_summary": profile.get("style_summary") or "",
        "body_types": sorted(profile.get("body_types") or []),
        "fit_preferences": sorted(profile.get("fit_preferences") or []),
        "favorite_colors": sorted(profile.get("favorite_colors") or []),
        "style_preferences": sorted(profile.get("style_preferences") or []),
    }
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def build_cache_key(user_id: str, messages: list, closet_hash: str, profile_hash: str = "") -> str:
    recent = messages[-3:]
    messages_json = json.dumps(recent, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(
        f"{user_id}:{messages_json}:{closet_hash}:{profile_hash}".encode("utf-8")
    ).hexdigest()
    return f"ai_cache:{user_id}:{digest}"


async def get_cached_response(redis: aioredis.Redis, cache_key: str) -> str | None:
    value = await redis.get(cache_key)
    return value if isinstance(value, str) else None


async def cache_response(redis: aioredis.Redis, cache_key: str, response: str, ttl: int = 600) -> None:
    await redis.set(cache_key, response, ex=ttl)


async def invalidate_user_ai_cache(redis: aioredis.Redis, user_id: str) -> int:
    pattern = f"ai_cache:{user_id}:*"
    deleted = 0
    async for key in redis.scan_iter(match=pattern, count=100):
        deleted += await redis.delete(key)
    return deleted
