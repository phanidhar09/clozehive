"""
WebSocket endpoint — real-time notifications and streaming.

Supported message types (client → server):
  { "type": "ping" }
  { "type": "subscribe", "channel": "closet" | "social" | "ai" }
  { "type": "chat", "message": "..." }

Server → client push events:
  { "type": "pong" }
  { "type": "subscribed", "channel": "..." }
  { "type": "notification", "channel": "...", "data": {...} }
  { "type": "chat_token", "content": "..." }
  { "type": "chat_done", "reply": "..." }
  { "type": "error", "message": "..." }
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from app.core.security import decode_access_token
from app.services import cache_service
from app.services.ai_client import stream_chat as ai_stream_chat

logger = structlog.get_logger("ws")
router = APIRouter(prefix="/ws", tags=["websocket"])

# ─────────────────────────────────────────────────────────────────────────────
#  Connection manager
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """Track local sockets and bridge cross-instance broadcasts through Redis."""

    def __init__(self) -> None:
        # user_id → list of active sockets
        self._connections: dict[str, list[WebSocket]] = {}
        self._listener_task: asyncio.Task | None = None
        self._listener_lock = asyncio.Lock()
        self._pubsub = None

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        await ws.accept()
        await self.ensure_listener()
        self._connections.setdefault(user_id, []).append(ws)
        logger.info("ws_connected", user_id=user_id, total=self._total())

    def disconnect(self, ws: WebSocket, user_id: str) -> None:
        sockets = self._connections.get(user_id, [])
        if ws in sockets:
            sockets.remove(ws)
        if not sockets:
            self._connections.pop(user_id, None)
        logger.info("ws_disconnected", user_id=user_id, total=self._total())

    async def send(self, ws: WebSocket, data: dict[str, Any]) -> None:
        try:
            await ws.send_json(data)
        except Exception:
            pass  # socket already gone

    async def broadcast_to_user(self, user_id: str, data: dict[str, Any]) -> None:
        """Publish a user-scoped message so every API instance can deliver it."""
        await self.publish_user(user_id, data)

    async def broadcast_all(self, data: dict[str, Any]) -> None:
        """Publish a global message so every API instance can deliver it."""
        await self.publish_all(data)

    async def publish_user(self, user_id: str, data: dict[str, Any]) -> None:
        client = await cache_service.get_redis()
        await client.publish(
            cache_service.websocket_user_channel(user_id),
            json.dumps({"user_id": user_id, "data": data}, default=str),
        )

    async def publish_all(self, data: dict[str, Any]) -> None:
        client = await cache_service.get_redis()
        await client.publish(
            cache_service.websocket_broadcast_channel(),
            json.dumps({"data": data}, default=str),
        )

    async def _deliver_to_user(self, user_id: str, data: dict[str, Any]) -> None:
        for ws in list(self._connections.get(user_id, [])):
            await self.send(ws, data)

    async def _deliver_all(self, data: dict[str, Any]) -> None:
        for sockets in list(self._connections.values()):
            for ws in list(sockets):
                await self.send(ws, data)

    def connected_users(self) -> list[str]:
        return list(self._connections.keys())

    def _total(self) -> int:
        return sum(len(s) for s in self._connections.values())

    async def ensure_listener(self) -> None:
        """Start one Redis Pub/Sub listener per worker process."""
        if self._listener_task and not self._listener_task.done():
            return
        async with self._listener_lock:
            if self._listener_task and not self._listener_task.done():
                return
            self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        while True:
            try:
                client = await cache_service.get_redis()
                self._pubsub = client.pubsub(ignore_subscribe_messages=True)
                await self._pubsub.psubscribe(cache_service.namespaced_key("ws", "user", "*"))
                await self._pubsub.subscribe(cache_service.websocket_broadcast_channel())
                logger.info("ws_pubsub_listener_started")

                async for message in self._pubsub.listen():
                    if message.get("type") not in {"message", "pmessage"}:
                        continue
                    try:
                        payload = json.loads(message.get("data") or "{}")
                    except json.JSONDecodeError:
                        logger.warning("ws_pubsub_malformed_payload")
                        continue

                    user_id = payload.get("user_id")
                    data = payload.get("data") or {}
                    if user_id:
                        await self._deliver_to_user(str(user_id), data)
                    else:
                        await self._deliver_all(data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("ws_pubsub_listener_error", error=str(exc))
                await asyncio.sleep(2)


manager = ConnectionManager()


# ─────────────────────────────────────────────────────────────────────────────
#  Token auth helper
# ─────────────────────────────────────────────────────────────────────────────

def _authenticate(token: str | None) -> str | None:
    """Return user_id from JWT token, or None if invalid."""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        return payload.get("sub")
    except (JWTError, Exception):
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Message handlers
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_ping(ws: WebSocket) -> None:
    await manager.send(ws, {"type": "pong", "ts": time.time()})


async def _handle_subscribe(ws: WebSocket, channel: str) -> None:
    valid = {"closet", "social", "ai", "notifications"}
    if channel not in valid:
        await manager.send(ws, {"type": "error", "message": f"Unknown channel '{channel}'"})
        return
    await manager.send(ws, {"type": "subscribed", "channel": channel})


async def _handle_chat(ws: WebSocket, user_id: str, message: str) -> None:
    """Stream an AI chat reply token by token over the WebSocket."""
    if not message.strip():
        await manager.send(ws, {"type": "error", "message": "message cannot be empty"})
        return

    try:
        reply_parts: list[str] = []
        async for event in ai_stream_chat(message=message, user_id=user_id):
            event_type = event.get("type")
            if event_type == "token":
                token = str(event.get("content", ""))
                reply_parts.append(token)
                await manager.send(ws, {"type": "chat_token", "content": token})
            elif event_type == "error":
                await manager.send(ws, {"type": "error", "message": event.get("message", "AI error")})
            elif event_type == "done":
                break
        await manager.send(ws, {"type": "chat_done", "reply": "".join(reply_parts)})
    except Exception as exc:
        logger.error("ws_chat_error", user_id=user_id, error=str(exc))
        await manager.send(ws, {"type": "error", "message": "AI service unavailable"})


# ─────────────────────────────────────────────────────────────────────────────
#  Main WebSocket route
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("")
async def websocket_endpoint(
    ws: WebSocket,
    token: str | None = None,
) -> None:
    """
    Main WebSocket endpoint.

    Connect: ws://host/ws?token=<access_token>

    The token is validated on connect. If invalid, the connection is closed
    with 4001 (unauthorized).
    """
    user_id = _authenticate(token)
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(ws, user_id)

    # Send welcome
    await manager.send(ws, {
        "type": "connected",
        "user_id": user_id,
        "message": "Welcome to ClozeHive real-time channel",
    })

    try:
        while True:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=300)

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(ws, {"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")
            logger.debug("ws_message", user_id=user_id, type=msg_type)

            match msg_type:
                case "ping":
                    await _handle_ping(ws)
                case "subscribe":
                    await _handle_subscribe(ws, msg.get("channel", ""))
                case "chat":
                    await _handle_chat(ws, user_id, msg.get("message", ""))
                case _:
                    await manager.send(ws, {
                        "type": "error",
                        "message": f"Unknown message type: '{msg_type}'",
                    })

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        # No message in 5 min — close cleanly
        await ws.close(code=1000, reason="Idle timeout")
    except Exception as exc:
        logger.error("ws_unexpected_error", user_id=user_id, error=str(exc))
    finally:
        manager.disconnect(ws, user_id)
