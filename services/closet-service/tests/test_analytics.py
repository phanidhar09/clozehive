"""Closet analytics — aggregates over the user's wardrobe (pure DB, no AI)."""

from __future__ import annotations

from httpx import AsyncClient

_ITEM = {"name": "Tee", "category": "tops", "color": "white", "season": ["summer"]}


async def test_analytics_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/analytics/closet")
    assert resp.status_code == 401


async def test_analytics_empty_closet(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/analytics/closet", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["total_items"] == 0
    assert isinstance(body["category_coverage"], list)


async def test_analytics_counts_items(client: AsyncClient, auth_headers) -> None:
    for color in ("white", "black", "white"):
        r = await client.post("/api/v1/closet/", json={**_ITEM, "color": color}, headers=auth_headers)
        assert r.status_code == 201, r.text

    resp = await client.get("/api/v1/analytics/closet", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["total_items"] == 3
    # All three are tops → tops should be the strongest category.
    assert body["summary"]["strongest_category"] == "tops"
    # white appears twice, black once → most common colour is white.
    assert body["summary"]["most_common_color"] == "white"
