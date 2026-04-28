"""
WebSocket endpoint handler.
Handles the connection lifecycle, authentication, and message routing.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.security import TokenError, decode_token
from app.websockets.manager import ws_manager

logger = logging.getLogger("clozehive.ws.handler")


async def _authenticate_ws(websocket: WebSocket) -> Optional[int]:
    """
    Authenticate a WebSocket connection.
    Token is passed as query param: ws://host/ws/{user_id}?token=<access_jwt>
    or as first message: {"type": "auth", "token": "<jwt>"}
    """
    # Try query param first
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = decode_token(token, expected_type="access")
            return int(payload["sub"])
        except (TokenError, ValueError):
            return None
    return None


async def websocket_endpoint(websocket: WebSocket, user_id: int) -> None:
    """
    Main WebSocket handler.

    URL: ws://localhost:8000/ws/{user_id}?token=<jwt>

    Client → Server message format:
        {"type": "ping"}
        {"type": "subscribe", "channel": "group:42"}

    Server → Client message format:
        {"type": "pong"}
        {"type": "follower_update", "follower_count": 12, ...}
        {"type": "group_update", "group_id": 42, ...}
        {"type": "login_broadcast", "username": "...", ...}
    """
    # Authenticate
    authed_id = await _authenticate_ws(websocket)

    if authed_id is None:
        # Accept the connection to send a proper error, then close
        await websocket.accept()
        await websocket.send_json({"type": "error", "detail": "Authentication required"})
        await websocket.close(code=4001)
        return

    if authed_id != user_id:
        await websocket.accept()
        await websocket.send_json({"type": "error", "detail": "Token user_id mismatch"})
        await websocket.close(code=4003)
        return

    # Register connection
    await ws_manager.connect(websocket, user_id)

    # Send welcome
    await websocket.send_json({
        "type": "connected",
        "user_id": user_id,
        "message": "WebSocket connected to CLOZEHIVE",
    })

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            await _handle_client_message(websocket, user_id, msg)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Unexpected WS error for user_id=%d: %s", user_id, exc)
    finally:
        await ws_manager.disconnect(websocket, user_id)


async def _handle_client_message(websocket: WebSocket, user_id: int, msg: dict) -> None:
    msg_type = msg.get("type")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    elif msg_type == "subscribe":
        # Client wants to subscribe to a group channel — just acknowledge
        channel = msg.get("channel", "")
        await websocket.send_json({"type": "subscribed", "channel": channel})

    elif msg_type == "message":
        # Echo back for now; could be extended for real-time chat
        await websocket.send_json({
            "type": "message_ack",
            "content": msg.get("content", ""),
            "from": user_id,
        })

    else:
        await websocket.send_json({"type": "error", "detail": f"Unknown message type: {msg_type}"})
