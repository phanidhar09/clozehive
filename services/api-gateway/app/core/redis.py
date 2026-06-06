"""Redis client and refresh-token session helpers."""

from __future__ import annotations

import hashlib

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()
_redis: aioredis.Redis | None = None
_state_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """General client for evictable cache data (cache invalidation, AI/vision cache)."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.effective_redis_cache_url, encoding="utf-8", decode_responses=True
        )
    return _redis


async def get_state_redis() -> aioredis.Redis:
    """Client for non-evictable state (refresh tokens). Falls back to redis_url."""
    global _state_redis
    if _state_redis is None:
        _state_redis = aioredis.from_url(
            settings.effective_redis_state_url, encoding="utf-8", decode_responses=True
        )
    return _state_redis


def _refresh_key(token: str) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"refresh_token:{token_hash}"


async def store_refresh_token(redis: aioredis.Redis, user_id: str, token: str, ttl_seconds: int) -> None:
    await redis.setex(_refresh_key(token), ttl_seconds, user_id)


async def revoke_refresh_token(redis: aioredis.Redis, token: str) -> None:
    await redis.delete(_refresh_key(token))


async def is_refresh_token_valid(redis: aioredis.Redis, token: str) -> bool:
    return await redis.exists(_refresh_key(token)) == 1
