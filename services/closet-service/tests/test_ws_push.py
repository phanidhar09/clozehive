"""Real-time WebSocket push regression tests.

closet-service has no local WS hub — it reaches the user's browser by publishing
to the Redis channel the api-gateway hub subscribes to. A previous bug made the
push a silent no-op (it imported a non-existent ``app.api.v1.ws`` module), so
these lock in the correct behaviour:

  1. publish_ws targets the exact channel the gateway hub psubscribes to.
  2. publish_ws never raises (a dead Redis must not break the request).
  3. Creating a closet item emits an ``item_added`` event for the owner.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

import app.api.v1.closet as closet_mod
from app.services import cache_service


async def test_publish_ws_targets_gateway_channel(monkeypatch) -> None:
    published: list[tuple[str, str]] = []

    class RecordingRedis:
        async def publish(self, channel: str, message: str) -> None:
            published.append((channel, message))

    async def fake_get_redis() -> RecordingRedis:
        return RecordingRedis()

    monkeypatch.setattr(cache_service, "get_redis", fake_get_redis)

    await cache_service.publish_ws("user-123", {"type": "notification", "data": {"event": "x"}})

    assert len(published) == 1
    channel, message = published[0]
    # Must match the gateway hub's psubscribe pattern: clozehive:v1:ws:user:*
    assert channel == "clozehive:v1:ws:user:user-123"
    assert json.loads(message)["data"]["event"] == "x"


async def test_publish_ws_swallows_redis_errors(monkeypatch) -> None:
    async def boom() -> None:
        raise RuntimeError("redis down")

    monkeypatch.setattr(cache_service, "get_redis", boom)
    # Must not raise.
    await cache_service.publish_ws("user-123", {"event": "x"})


async def test_create_item_emits_item_added_event(client: AsyncClient, auth_headers, user_id, monkeypatch) -> None:
    pushes: list[tuple[str, dict]] = []

    async def capture(uid: str, data: dict) -> None:
        pushes.append((uid, data))

    # Override the conftest no-op so we can observe the push.
    monkeypatch.setattr(closet_mod, "_ws_push", capture)

    resp = await client.post(
        "/api/v1/closet/",
        json={"name": "Red Scarf", "category": "accessories", "color": "red"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    assert len(pushes) == 1
    pushed_uid, payload = pushes[0]
    assert pushed_uid == user_id
    assert payload["data"]["event"] == "item_added"
    assert payload["data"]["item_name"] == "Red Scarf"
