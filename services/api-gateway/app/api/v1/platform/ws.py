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
import secrets
import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.v1.intelligence.services.ai_client import stream_chat as ai_stream_chat
from app.core import cache_service
from app.core.deps import CurrentUser

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
        self._pubsub: Any = None

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
        # Best-effort delivery: a Redis outage must not take down the caller
        # (these run fire-and-forget), so swallow-and-log rather than propagate.
        try:
            client = await cache_service.get_redis()
            await client.publish(
                cache_service.websocket_user_channel(user_id),
                json.dumps({"user_id": user_id, "data": data}, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws_publish_user_failed", user_id=user_id, error=str(exc))

    async def publish_all(self, data: dict[str, Any]) -> None:
        try:
            client = await cache_service.get_redis()
            await client.publish(
                cache_service.websocket_broadcast_channel(),
                json.dumps({"data": data}, default=str),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws_publish_all_failed", error=str(exc))

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
        backoff = 2.0
        max_backoff = 60.0
        while True:
            # If nobody is connected, pause rather than hammering Redis.
            if self._total() == 0:
                await asyncio.sleep(5)
                continue
            try:
                client = await cache_service.get_redis()
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                self._pubsub = pubsub
                await pubsub.psubscribe(cache_service.namespaced_key("ws", "user", "*"))
                await pubsub.subscribe(cache_service.websocket_broadcast_channel())
                logger.info("ws_pubsub_listener_started")
                backoff = 2.0  # reset on successful connection

                async for message in pubsub.listen():
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
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)


manager = ConnectionManager()


# ─────────────────────────────────────────────────────────────────────────────
#  Ticket auth
#
#  Browsers can't set headers on a WebSocket handshake, so the classic
#  workaround is `?token=<jwt>` — which leaks the bearer token into access
#  logs, proxy logs, browser history, and Referer headers. Instead the client
#  exchanges its JWT (over a normal authenticated POST) for a short-lived
#  single-use ticket and connects with `?ticket=`. A leaked ticket is worthless
#  the moment the connection is made, and expires in seconds otherwise.
# ─────────────────────────────────────────────────────────────────────────────

_TICKET_TTL_S = 60


def _ticket_key(ticket: str) -> str:
    return cache_service.namespaced_key("ws", "ticket", ticket)


@router.post("/ticket")
async def create_ws_ticket(user_id: CurrentUser) -> dict[str, Any]:
    """Issue a single-use WebSocket connection ticket for the caller."""
    ticket = secrets.token_urlsafe(32)
    stored = await cache_service.set(_ticket_key(ticket), user_id, _TICKET_TTL_S)
    if not stored:
        raise HTTPException(status_code=503, detail="Realtime service unavailable, try again.")
    return {"ticket": ticket, "expires_in": _TICKET_TTL_S}


async def _consume_ticket(ticket: str | None) -> str | None:
    """Redeem a ticket exactly once (atomic GETDEL). Returns user_id or None."""
    if not ticket:
        return None
    user_id = await cache_service.getdel(_ticket_key(ticket))
    return str(user_id) if user_id else None


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
    ticket: str | None = None,
) -> None:
    """
    Main WebSocket endpoint.

    Connect: ws://host/ws?ticket=<ticket from POST /ws/ticket>

    The single-use ticket is consumed on connect. If missing, expired, or
    already used, the connection is closed with 4001 (unauthorized).
    """
    user_id = await _consume_ticket(ticket)
    if not user_id:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(ws, user_id)

    # Send welcome
    await manager.send(
        ws,
        {
            "type": "connected",
            "user_id": user_id,
            "message": "Welcome to ClozeHive real-time channel",
        },
    )

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
                    await manager.send(
                        ws,
                        {
                            "type": "error",
                            "message": f"Unknown message type: '{msg_type}'",
                        },
                    )

    except WebSocketDisconnect:
        pass
    except TimeoutError:
        # No message in 5 min — close cleanly
        await ws.close(code=1000, reason="Idle timeout")
    except Exception as exc:
        logger.error("ws_unexpected_error", user_id=user_id, error=str(exc))
    finally:
        manager.disconnect(ws, user_id)
