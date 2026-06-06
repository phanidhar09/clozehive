"""Lightweight process health (no database)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_live_returns_ok(async_client: AsyncClient):
    response = await async_client.get("/live")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "alive"


@pytest.mark.asyncio
async def test_rate_limit_response_shape():
    from unittest.mock import MagicMock

    from app.main import rate_limit_handler

    req = MagicMock()
    req.state.request_id = "test-req-id"
    resp = await rate_limit_handler(req, MagicMock())
    assert resp.status_code == 429
    import json

    data = json.loads(resp.body.decode())
    assert data.get("code") == "RATE_LIMITED"
    assert data.get("request_id") == "test-req-id"
    assert "detail" in data
