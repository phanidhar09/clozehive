"""Smoke test for the gated SSE chat route (POST /ai-chat/stream).

The legacy plain-text /ai/chat/stream route was removed — every chat UI now
consumes this path (model router, RAG, grounding gate, claim audit, telemetry).
This test locks the SSE contract: session → token(s) → structured → done.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

import app.api.v1.intelligence.ai_chat as ai_chat_routes
import app.api.v1.intelligence.services.ai_stylist_streaming as streaming
from tests.conftest import TestSessionLocal

_MOCK_MODEL_JSON = json.dumps(
    {
        "reply": "Hello from mocked AI.",
        "recommended_outfits": [],
        "styling_suggestions": [],
        "purchase_gaps": [],
        "follow_up_questions": [],
    }
)


@pytest.mark.asyncio
async def test_ai_chat_stream_smoke(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Stream User",
            "email": "stream@example.com",
            "username": "streamuser",
            "password": "Password1",
            "gdpr_consent": True,
        },
    )
    assert signup.status_code == 201
    token = signup.json()["access_token"]

    async def _fake_stream_chat(*args, **kwargs):
        yield _MOCK_MODEL_JSON

    async def _no_embedding(*args, **kwargs):
        return None  # forces the deterministic fallback-closet path

    monkeypatch.setattr(streaming.ai_service, "stream_chat", _fake_stream_chat)
    monkeypatch.setattr(streaming, "generate_text_embedding", _no_embedding)
    # The stream generator opens its own DB session (it outlives the request-
    # scoped one), so point its sessionmaker at the test database.
    monkeypatch.setattr(ai_chat_routes, "AsyncSessionLocal", TestSessionLocal)

    async with client.stream(
        "POST",
        "/api/v1/ai-chat/stream",
        json={"message": "What should I wear?", "session_id": None, "context": {}, "history": []},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        body = await resp.aread()

    events = [
        json.loads(line.removeprefix(b"data: ").decode())
        for line in body.split(b"\n\n")
        if line.startswith(b"data: ")
    ]
    kinds = [e.get("type") for e in events]

    # SSE contract: session first, at least one token, structured payload, done.
    assert kinds[0] == "session"
    assert "token" in kinds
    assert "structured" in kinds
    assert kinds[-1] == "done"

    reply_text = "".join(e.get("content", "") for e in events if e.get("type") == "token")
    assert "Hello from mocked AI." in reply_text

    structured = next(e for e in events if e.get("type") == "structured")
    assert structured.get("reply") == "Hello from mocked AI."
    # Grounding-audit fields shipped with the structured event.
    assert "quality" in structured
    assert "corrected" in structured
