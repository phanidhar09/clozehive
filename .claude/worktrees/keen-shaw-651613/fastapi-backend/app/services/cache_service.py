"""
Redis cache service — centralised caching abstraction.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("clozehive.cache")

# ── Singleton Redis client ────────────────────────────────────────────────────
_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# ── Key helpers ───────────────────────────────────────────────────────────────

class CacheKeys:
    @staticmethod
    def user_profile(user_id: int) -> str:
        return f"profile:{user_id}"

    @staticmethod
    def user_by_username(username: str) -> str:
        return f"username:{username}"

    @staticmethod
    def closet(user_id: int) -> str:
        return f"closet:{user_id}"

    @staticmethod
    def weather(location: str) -> str:
        loc_key = location.lower().replace(" ", "_")[:50]
        return f"weather:{loc_key}"

    @staticmethod
    def refresh_token(jti: str) -> str:
        return f"rt:{jti}"

    @staticmethod
    def rate_limit(identifier: str) -> str:
        return f"rl:{identifier}"


# ── Cache operations ─────────────────────────────────────────────────────────

class CacheService:
    def __init__(self) -> None:
        self._r = get_redis()

    async def get(self, key: str) -> Optional[Any]:
        try:
            raw = await self._r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Cache GET failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self._r.setex(key, ttl, json.dumps(value, default=str))
        except Exception as exc:
            logger.warning("Cache SET failed for key=%s: %s", key, exc)

    async def delete(self, *keys: str) -> None:
        try:
            if keys:
                await self._r.delete(*keys)
        except Exception as exc:
            logger.warning("Cache DELETE failed: %s", exc)

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self._r.exists(key))
        except Exception:
            return False

    # ── Pub/Sub for WebSockets ────────────────────────────────────────────────

    async def publish(self, channel: str, message: dict) -> None:
        try:
            await self._r.publish(channel, json.dumps(message, default=str))
        except Exception as exc:
            logger.warning("Redis PUBLISH failed on channel=%s: %s", channel, exc)

    def pubsub(self) -> aioredis.client.PubSub:
        return self._r.pubsub()


# ── Module-level singleton ────────────────────────────────────────────────────
cache = CacheService()
