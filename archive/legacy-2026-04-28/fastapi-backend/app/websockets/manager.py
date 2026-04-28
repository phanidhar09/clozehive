"""
WebSocket connection manager with Redis Pub/Sub for multi-instance broadcast.

Architecture:
  ┌─────────────┐    WS     ┌──────────────┐
  │  Browser    │ ◄──────── │  FastAPI     │
  └─────────────┘           │  Instance A  │
                             └──────┬───────┘
                                    │ publish
                             ┌──────▼───────┐
                             │    Redis     │
                             │   Pub/Sub    │
                             └──────┬───────┘
                                    │ subscribe
                             ┌──────▼───────┐
                             │  FastAPI     │
                             │  Instance B  │ ──► Browser
                             └──────────────┘
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.services.cache_service import get_redis

logger = logging.getLogger("clozehive.ws")


class ConnectionManager:
    """
    Manages active WebSocket connections and routes messages via Redis pub/sub.
    Thread-safe via asyncio locks.
    """

    def __init__(self) -> None:
        # user_id → set of active WebSocket connections
        self._connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._subscriber_task: Optional[asyncio.Task] = None

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)
        logger.info("WS connected: user_id=%d  total_connections=%d", user_id, self._total())

    async def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("WS disconnected: user_id=%d  total_connections=%d", user_id, self._total())

    def _total(self) -> int:
        return sum(len(s) for s in self._connections.values())

    # ── Send helpers ──────────────────────────────────────────────────────────

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        """Send a JSON message directly to all connections of a specific user."""
        sockets = set(self._connections.get(user_id, set()))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(payload)
            except Exception as exc:
                logger.debug("WS send failed: %s", exc)
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, user_id)

    async def broadcast(self, payload: dict) -> None:
        """Broadcast to ALL connected users."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, payload)

    async def broadcast_to_group(self, group_member_ids: list[int], payload: dict) -> None:
        """Broadcast to a set of user ids (e.g., group members)."""
        for uid in group_member_ids:
            await self.send_to_user(uid, payload)

    # ── Redis Pub/Sub subscriber (runs as background task) ────────────────────

    async def start_redis_subscriber(self) -> None:
        """
        Subscribe to Redis channels and forward messages to local WebSocket clients.
        Channel conventions:
          user:{user_id}   → messages for a specific user
          group:{group_id} → messages for all members of a group
          broadcast        → messages for all connected users
        """
        if self._subscriber_task and not self._subscriber_task.done():
            return

        self._subscriber_task = asyncio.create_task(self._redis_listener())
        logger.info("Redis pub/sub listener started.")

    async def _redis_listener(self) -> None:
        redis = get_redis()
        pubsub = redis.pubsub()

        try:
            await pubsub.psubscribe(
                "user:*",
                "group:*",
                "broadcast",
            )
            logger.info("Subscribed to Redis channels: user:*, group:*, broadcast")

            async for raw_msg in pubsub.listen():
                if raw_msg["type"] not in ("pmessage", "message"):
                    continue

                channel: str = raw_msg.get("channel", "") or ""
                try:
                    payload = json.loads(raw_msg.get("data", "{}"))
                except (json.JSONDecodeError, TypeError):
                    continue

                await self._route_redis_message(channel, payload)

        except asyncio.CancelledError:
            logger.info("Redis pub/sub listener stopped.")
        except Exception as exc:
            logger.error("Redis listener error: %s", exc)
        finally:
            try:
                await pubsub.punsubscribe()
                await pubsub.aclose()
            except Exception:
                pass

    async def _route_redis_message(self, channel: str, payload: dict) -> None:
        if channel == "broadcast":
            await self.broadcast(payload)

        elif channel.startswith("user:"):
            try:
                user_id = int(channel.split(":", 1)[1])
                await self.send_to_user(user_id, payload)
            except (ValueError, IndexError):
                pass

        elif channel.startswith("group:"):
            # The payload should carry a list of member_ids, or we look it up
            member_ids: list[int] = payload.get("member_ids", [])
            await self.broadcast_to_group(member_ids, payload)

    async def stop(self) -> None:
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass


# ── Module-level singleton ────────────────────────────────────────────────────
ws_manager = ConnectionManager()
