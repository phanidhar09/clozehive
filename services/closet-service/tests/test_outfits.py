"""Saved-outfit CRUD + item-ownership validation.

The AI path (POST /outfits/generate) is intentionally not covered here — it
returns a deeply-nested ScoredOutfit that's brittle to stub. These tests cover
the deterministic saved-outfit endpoints and the ownership guard.
"""

from __future__ import annotations

from httpx import AsyncClient

_ITEM = {"name": "Black Jeans", "category": "bottoms", "color": "black", "season": ["all-season"]}


async def _create_item(client: AsyncClient, headers: dict[str, str], **overrides) -> str:
    resp = await client.post("/api/v1/closet/", json={**_ITEM, **overrides}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Auth ────────────────────────────────────────────────────────────────────

async def test_list_outfits_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/outfits/")
    assert resp.status_code == 401


# ── Create + list ─────────────────────────────────────────────────────────────

async def test_empty_outfits_list(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/outfits/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_outfit_from_owned_items(client: AsyncClient, auth_headers) -> None:
    top = await _create_item(client, auth_headers, name="White Tee", category="tops")
    bottom = await _create_item(client, auth_headers, name="Black Jeans", category="bottoms")

    resp = await client.post(
        "/api/v1/outfits/",
        json={"name": "Casual Friday", "item_ids": [top, bottom], "occasion": "casual"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Casual Friday"
    assert set(body["item_ids"]) == {top, bottom}
    assert body["is_saved"] is True

    listing = await client.get("/api/v1/outfits/", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["id"] == body["id"]


# ── Validation ────────────────────────────────────────────────────────────────

async def test_create_outfit_empty_items_rejected(client: AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/outfits/",
        json={"name": "Empty", "item_ids": [], "occasion": "casual"},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # item_ids has min_length=1


async def test_create_outfit_with_unowned_item_rejected(client: AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/outfits/",
        json={
            "name": "Borrowed",
            "item_ids": ["00000000-0000-0000-0000-000000000000"],
            "occasion": "casual",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400  # item not in the user's closet


async def test_cannot_use_another_users_item_in_outfit(
    client: AsyncClient, auth_headers, other_user_headers
) -> None:
    # Item owned by the first user…
    other_item = await _create_item(client, auth_headers, name="Owner's Coat", category="outerwear")
    # …cannot be referenced by a second user's outfit.
    resp = await client.post(
        "/api/v1/outfits/",
        json={"name": "Theft", "item_ids": [other_item], "occasion": "casual"},
        headers=other_user_headers,
    )
    assert resp.status_code == 400


# ── Isolation ─────────────────────────────────────────────────────────────────

async def test_outfits_are_user_scoped(client: AsyncClient, auth_headers, other_user_headers) -> None:
    top = await _create_item(client, auth_headers, name="Tee", category="tops")
    await client.post(
        "/api/v1/outfits/",
        json={"name": "Mine", "item_ids": [top], "occasion": "casual"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/outfits/", headers=other_user_headers)
    assert resp.status_code == 200
    assert resp.json() == []
