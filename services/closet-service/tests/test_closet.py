"""Closet CRUD, wear logging, auth, and cross-user isolation.

These exercise the wardrobe domain closet-service now owns. They use a SQLite
in-memory DB and fake Redis (see conftest) — no external services.
"""

from __future__ import annotations

from httpx import AsyncClient

NEW_ITEM = {
    "name": "Navy Oxford Shirt",
    "category": "tops",
    "color": "navy",
    "season": ["all-season"],
    "occasion": ["business"],
    "brand": "Uniqlo",
}


async def _create(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload = {**NEW_ITEM, **overrides}
    resp = await client.post("/api/v1/closet/", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Auth ────────────────────────────────────────────────────────────────────

async def test_list_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/closet/")
    assert resp.status_code == 401


async def test_create_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/closet/", json=NEW_ITEM)
    assert resp.status_code == 401


async def test_invalid_token_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/closet/", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


# ── Create + read ─────────────────────────────────────────────────────────────

async def test_create_item_returns_201_with_fields(client: AsyncClient, auth_headers, user_id) -> None:
    item = await _create(client, auth_headers)
    assert item["name"] == NEW_ITEM["name"]
    assert item["category"] == "tops"
    assert item["color"] == "navy"
    assert item["user_id"] == user_id
    assert item["wear_count"] == 0
    assert item["is_archived"] is False
    assert "id" in item


async def test_created_item_appears_in_list(client: AsyncClient, auth_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.get("/api/v1/closet/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


async def test_get_item_by_id(client: AsyncClient, auth_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.get(f"/api/v1/closet/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_missing_item_returns_404(client: AsyncClient, auth_headers) -> None:
    resp = await client.get(
        "/api/v1/closet/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_create_rejects_invalid_category(client: AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/closet/", json={**NEW_ITEM, "category": "spaceship"}, headers=auth_headers
    )
    assert resp.status_code == 422


# ── Update + delete + wear ────────────────────────────────────────────────────

async def test_patch_item_updates_fields(client: AsyncClient, auth_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.patch(
        f"/api/v1/closet/{created['id']}", json={"color": "charcoal"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["color"] == "charcoal"


async def test_delete_item_then_404(client: AsyncClient, auth_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.delete(f"/api/v1/closet/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    follow = await client.get(f"/api/v1/closet/{created['id']}", headers=auth_headers)
    assert follow.status_code == 404


async def test_log_wear_increments_count(client: AsyncClient, auth_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.post(f"/api/v1/closet/{created['id']}/wear", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["wear_count"] == created["wear_count"] + 1


# ── Cross-user isolation ──────────────────────────────────────────────────────

async def test_other_user_cannot_see_item(client: AsyncClient, auth_headers, other_user_headers) -> None:
    await _create(client, auth_headers)
    resp = await client.get("/api/v1/closet/", headers=other_user_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_other_user_cannot_get_item(client: AsyncClient, auth_headers, other_user_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.get(f"/api/v1/closet/{created['id']}", headers=other_user_headers)
    assert resp.status_code == 404


async def test_other_user_cannot_delete_item(client: AsyncClient, auth_headers, other_user_headers) -> None:
    created = await _create(client, auth_headers)
    resp = await client.delete(f"/api/v1/closet/{created['id']}", headers=other_user_headers)
    assert resp.status_code == 404
    # Owner still has it.
    still = await client.get(f"/api/v1/closet/{created['id']}", headers=auth_headers)
    assert still.status_code == 200
