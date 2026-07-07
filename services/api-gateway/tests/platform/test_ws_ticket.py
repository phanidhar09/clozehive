"""Tests for the single-use WebSocket connect ticket (replaces ?token=<jwt>)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.platform import ws


@pytest.fixture
def ticket_store(monkeypatch):
    """In-memory stand-in for the Redis-backed ticket store."""
    store: dict[str, str] = {}

    async def fake_set(key, value, ttl):
        assert ttl == ws._TICKET_TTL_S
        store[key] = value
        return True

    async def fake_getdel(key):
        return store.pop(key, None)

    monkeypatch.setattr(ws.cache_service, "set", fake_set)
    monkeypatch.setattr(ws.cache_service, "getdel", fake_getdel)
    return store


@pytest.mark.asyncio
async def test_ticket_roundtrip_is_single_use(ticket_store):
    out = await ws.create_ws_ticket("user-1")
    assert out["expires_in"] == ws._TICKET_TTL_S
    ticket = out["ticket"]
    assert len(ticket) >= 32

    # First redemption authenticates; the second must fail (GETDEL semantics).
    assert await ws._consume_ticket(ticket) == "user-1"
    assert await ws._consume_ticket(ticket) is None


@pytest.mark.asyncio
async def test_missing_or_unknown_ticket_rejected(ticket_store):
    assert await ws._consume_ticket(None) is None
    assert await ws._consume_ticket("") is None
    assert await ws._consume_ticket("not-a-real-ticket") is None


@pytest.mark.asyncio
async def test_ticket_issue_fails_closed_when_store_down(monkeypatch):
    async def failing_set(key, value, ttl):
        return False

    monkeypatch.setattr(ws.cache_service, "set", failing_set)
    with pytest.raises(HTTPException) as exc:
        await ws.create_ws_ticket("user-1")
    assert exc.value.status_code == 503
