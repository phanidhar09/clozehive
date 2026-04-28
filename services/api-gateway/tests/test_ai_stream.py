"""SSE streaming routes for /ai/* — smoke tests with mocked AI client."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

import app.api.v1.ai as ai_routes


@pytest.mark.asyncio
async def test_chat_stream_smoke(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Stream User",
            "email": "stream@example.com",
            "username": "streamuser",
            "password": "Password1",
        },
    )
    assert signup.status_code == 201
    token = signup.json()["access_token"]

    async def _fake_stream_chat(*args, **kwargs):
        yield {"type": "token", "content": "Hello from mocked AI."}
        yield {"type": "done"}

    monkeypatch.setattr(ai_routes.ai_client, "stream_chat", _fake_stream_chat)

    async with client.stream(
        "POST",
        "/api/v1/ai/chat/stream",
        json={"message": "What should I wear?", "history": [], "include_closet": False},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        body = await resp.aread()
        assert b"data:" in body
        assert b"Hello from mocked AI" in body
        assert b'"type": "done"' in body
