"""
Redis cache service — typed helpers with automatic TTL and JSON serialisation.
Gracefully degrades (logs warning, returns None) when Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, datetime
from enum import Enum
from typing import Any, cast

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("cache")
settings = get_settings()

_redis: aioredis.Redis | None = None
_state_redis: aioredis.Redis | None = None
_KEY_PREFIX = "clozehive:v1"


def namespaced_key(*parts: str) -> str:
    """Build a stable Redis key namespace shared across gateway instances."""
    safe_parts = [str(part).strip().replace(" ", "_") for part in parts if str(part).strip()]
    return ":".join([_KEY_PREFIX, *safe_parts])


def _new_client(url: str) -> aioredis.Redis:
    return aioredis.from_url(
        url,
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


async def get_redis() -> aioredis.Redis:
    """Client for evictable cache data (allkeys-lru is safe here)."""
    global _redis
    if _redis is None:
        _redis = _new_client(settings.effective_redis_cache_url)
    return _redis


async def get_state_redis() -> aioredis.Redis:
    """Client for non-evictable state (OAuth CSRF/code, refresh tokens).

    Points at the state Redis (noeviction). Falls back to the shared redis_url
    when no dedicated state instance is configured, so single-Redis setups are
    unchanged. Use the ``state_*`` helpers below rather than this client directly.
    """
    global _state_redis
    if _state_redis is None:
        _state_redis = _new_client(settings.effective_redis_state_url)
    return _state_redis


async def get(key: str) -> Any | None:
    from app.core.metrics import record_cache

    try:
        client = await get_redis()
        value = await client.get(key)
        if value is None:
            record_cache("miss")
            return None
        record_cache("hit")
        return json.loads(value)
    except Exception as exc:
        record_cache("error")
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


async def getdel(key: str) -> Any | None:
    """Atomically GET the value at *key* and DELETE it in one round-trip.

    Uses the native Redis GETDEL command (Redis ≥ 6.2 / Valkey) with a Lua
    script fallback for older servers.  This is the correct primitive for
    single-use tokens (OAuth codes, password-reset tokens) because a plain
    GET followed by a separate DELETE leaves a window where two concurrent
    callers can both see the value before either deletes it.
    """
    try:
        client = await get_redis()
        # Try the native command first (Redis 6.2+, Valkey 7+).
        try:
            raw = await client.getdel(key)
        except Exception:
            # Fallback: atomic GET + DEL via Lua so older servers still work.
            lua = """
local v = redis.call('GET', KEYS[1])
if v then redis.call('DEL', KEYS[1]) end
return v
"""
            raw = await cast("Awaitable[str]", client.eval(lua, 1, key))

        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("cache_getdel_error", key=key, error=str(exc))
        return None


async def delete(key: str) -> None:
    try:
        client = await get_redis()
        await client.delete(key)
    except Exception as exc:
        logger.warning("cache_delete_error", key=key, error=str(exc))


# ── Single-flight lock + stale-while-revalidate compute ───────────────────────


async def acquire_lock(key: str, ttl: int = 10) -> bool:
    """Best-effort single-flight lock (SET NX EX). True = caller owns the lock.

    On Redis error returns True so the caller proceeds to compute rather than
    stalling — correctness (a value is produced) over the optimisation.
    """
    try:
        client = await get_redis()
        return bool(await client.set(f"lock:{key}", "1", nx=True, ex=ttl))
    except Exception:
        return True


async def release_lock(key: str) -> None:
    try:
        client = await get_redis()
        await client.delete(f"lock:{key}")
    except Exception:
        pass


async def get_or_compute(
    key: str,
    ttl: int,
    compute: Callable[[], Awaitable[Any]],
    *,
    swr_seconds: int | None = None,
    lock_ttl: int = 10,
    negative_ttl: int = 0,
) -> Any:
    """Cache-aside with stale-while-revalidate + single-flight stampede control.

    The value is stored wrapped with a soft-expiry timestamp; the Redis key lives
    for ``ttl + swr_seconds`` (the hard TTL).

    - Fresh (now < soft expiry): return cached value.
    - Stale (soft expired, hard alive): return the stale value immediately AND
      kick off a background refresh — but only the one caller that wins the lock
      refreshes; everyone else serves stale. Eliminates the thundering herd.
    - Missing: the lock winner computes synchronously; losers briefly wait then
      read the now-populated value (falling back to compute if still absent).

    ``compute`` MUST be self-contained (open its own DB/HTTP resources) because it
    may run in a background task after the request session has closed.
    ``negative_ttl`` > 0 caches a ``None`` result for that many seconds to absorb
    repeated misses (negative caching).
    """
    soft = ttl
    hard = ttl + (swr_seconds if swr_seconds is not None else 0)

    wrapped = await get(key)
    now = time.time()

    if isinstance(wrapped, dict) and "__swr__" in wrapped:
        value = wrapped.get("v")
        soft_exp = wrapped.get("exp", 0)
        if now < soft_exp:
            return value  # fresh
        # Stale — serve it, refresh in the background under single-flight.
        if await acquire_lock(key, lock_ttl):
            asyncio.create_task(_refresh(key, soft, hard, compute, negative_ttl))
        return value

    # Cold miss — single-flight so only one caller computes.
    if await acquire_lock(key, lock_ttl):
        try:
            return await _compute_and_store(key, soft, hard, compute, negative_ttl)
        finally:
            await release_lock(key)

    # Lost the race: wait briefly for the winner to populate, then read.
    for _ in range(int(lock_ttl * 10)):
        await asyncio.sleep(0.1)
        wrapped = await get(key)
        if isinstance(wrapped, dict) and "__swr__" in wrapped:
            return wrapped.get("v")
    # Winner still hasn't produced — compute ourselves rather than fail.
    return await _compute_and_store(key, soft, hard, compute, negative_ttl)


async def _compute_and_store(key, soft, hard, compute, negative_ttl) -> Any:
    value = await compute()
    if value is None and negative_ttl <= 0:
        return None
    store_ttl = hard if value is not None else negative_ttl
    soft_window = soft if value is not None else negative_ttl
    await set(key, {"__swr__": 1, "v": value, "exp": time.time() + soft_window}, store_ttl)
    return value


async def _refresh(key, soft, hard, compute, negative_ttl) -> None:
    try:
        await _compute_and_store(key, soft, hard, compute, negative_ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_swr_refresh_failed", key=key, error=str(exc))
    finally:
        await release_lock(key)


async def warm(key: str, value: Any, ttl: int, *, swr_seconds: int = 0) -> None:
    """Write-through cache warming in the get_or_compute format.

    Call after a write to pre-populate the cache so the next read is hot instead
    of cold (e.g. after updating a profile). Stored in the same ``__swr__`` wrapper
    so a later get_or_compute treats it as fresh until the soft TTL elapses.
    """
    await set(key, {"__swr__": 1, "v": value, "exp": time.time() + ttl}, ttl + swr_seconds)


# ── State helpers (non-evictable Redis) ───────────────────────────────────────
# Mirror get/set/getdel/delete but target the state Redis. Use these for data
# that must survive memory pressure: OAuth CSRF state, OAuth code→token exchange,
# and any other single-use security token kept in Redis.


async def state_get(key: str) -> Any | None:
    try:
        client = await get_state_redis()
        value = await client.get(key)
        return json.loads(value) if value is not None else None
    except Exception as exc:
        logger.warning("state_get_error", key=key, error=str(exc))
        return None


async def state_set(key: str, value: Any, ttl: int) -> bool:
    """Set a JSON value with TTL on the state Redis. Returns True on ack.

    Callers that cannot proceed without the write (e.g. OAuth CSRF state) should
    check the return value and fail closed when it is False.
    """
    try:
        client = await get_state_redis()
        ok = await client.setex(key, ttl, json.dumps(value, default=str))
        return bool(ok)
    except Exception as exc:
        logger.warning("state_set_error", key=key, error=str(exc))
        return False


async def state_getdel(key: str) -> Any | None:
    """Atomic GET+DELETE on the state Redis (single-use tokens)."""
    try:
        client = await get_state_redis()
        try:
            raw = await client.getdel(key)
        except Exception:
            lua = """
local v = redis.call('GET', KEYS[1])
if v then redis.call('DEL', KEYS[1]) end
return v
"""
            raw = await cast("Awaitable[str]", client.eval(lua, 1, key))
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.warning("state_getdel_error", key=key, error=str(exc))
        return None


async def state_delete(key: str) -> None:
    try:
        client = await get_state_redis()
        await client.delete(key)
    except Exception as exc:
        logger.warning("state_delete_error", key=key, error=str(exc))


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
    global _redis, _state_redis
    if _redis:
        await _redis.aclose()
        _redis = None
    if _state_redis:
        await _state_redis.aclose()
        _state_redis = None


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
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def build_cache_key(user_id: str, messages: list, closet_hash: str, profile_hash: str = "") -> str:
    recent = messages[-3:]
    messages_json = json.dumps(recent, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{user_id}:{messages_json}:{closet_hash}:{profile_hash}".encode()).hexdigest()
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
