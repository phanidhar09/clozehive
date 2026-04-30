"""Unit tests for closet endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.api.v1 import closet as closet_routes


async def _auth_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post("/api/v1/auth/signup", json={
        "name": f"Closet User{suffix}",
        "email": f"closet{suffix}@example.com",
        "username": f"closetuser{suffix}",
        "password": "Password1",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_and_list_item(client: AsyncClient):
    headers = await _auth_headers(client, "1")

    create_resp = await client.post("/api/v1/closet/", json={
        "name": "White T-Shirt",
        "category": "tops",
        "color": "white",
        "fabric": "cotton",
    }, headers=headers)
    assert create_resp.status_code == 201
    item = create_resp.json()
    assert item["name"] == "White T-Shirt"
    assert item["category"] == "tops"

    list_resp = await client.get("/api/v1/closet/", headers=headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == item["id"]


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient):
    headers = await _auth_headers(client, "2")
    resp = await client.get("/api/v1/closet/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_item(client: AsyncClient):
    headers = await _auth_headers(client, "3")
    create = await client.post("/api/v1/closet/", json={
        "name": "Blue Jeans",
        "category": "bottoms",
    }, headers=headers)
    item_id = create.json()["id"]

    update = await client.patch(f"/api/v1/closet/{item_id}", json={"color": "dark blue"}, headers=headers)
    assert update.status_code == 200
    assert update.json()["color"] == "dark blue"


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient):
    headers = await _auth_headers(client, "4")
    create = await client.post("/api/v1/closet/", json={
        "name": "Old Jacket",
        "category": "outerwear",
    }, headers=headers)
    item_id = create.json()["id"]

    del_resp = await client.delete(f"/api/v1/closet/{item_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/closet/{item_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_access_other_users_item(client: AsyncClient):
    headers_a = await _auth_headers(client, "5a")
    headers_b = await _auth_headers(client, "5b")

    create = await client.post("/api/v1/closet/", json={
        "name": "Private Shirt",
        "category": "tops",
    }, headers=headers_a)
    item_id = create.json()["id"]

    resp = await client.get(f"/api/v1/closet/{item_id}", headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_log_wear(client: AsyncClient):
    headers = await _auth_headers(client, "6")
    create = await client.post("/api/v1/closet/", json={
        "name": "Sneakers",
        "category": "shoes",
    }, headers=headers)
    item_id = create.json()["id"]

    resp = await client.post(f"/api/v1/closet/{item_id}/wear", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["wear_count"] == 1


@pytest.mark.asyncio
async def test_upload_persists_image_url(client: AsyncClient, monkeypatch, tmp_path):
    headers = await _auth_headers(client, "7")

    async def fake_analyze_image(_image_bytes: bytes, _media_type: str) -> dict:
        return {"name": "Uploaded Shirt", "category": "tops", "color": "white"}

    monkeypatch.setattr(closet_routes.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(closet_routes.ai_client, "analyze_image", fake_analyze_image)

    resp = await client.post(
        "/api/v1/closet/upload",
        files={"file": ("shirt.jpg", b"fake image bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    image_url = resp.json()["item"]["image_url"]
    assert image_url.startswith("/uploads/")
    assert (tmp_path / image_url.removeprefix("/uploads/")).exists()
