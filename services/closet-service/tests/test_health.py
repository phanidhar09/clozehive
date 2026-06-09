"""Smoke tests — process liveness and the JSON root, no DB/Redis needed."""

from __future__ import annotations

from httpx import AsyncClient


async def test_live_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") in {"ok", "alive", "live", "up"} or body.get("alive") is True


async def test_root_describes_service(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "service" in body
    assert body.get("endpoints", {}).get("api_v1") == "/api/v1"
