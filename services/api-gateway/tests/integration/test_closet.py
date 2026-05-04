import pytest
from httpx import AsyncClient


async def headers_for(async_client: AsyncClient, prefix: str) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "name": f"{prefix} User",
            "email": f"{prefix}@example.com",
            "username": f"{prefix}user",
            "password": "Password1",
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_item(async_client: AsyncClient, headers: dict[str, str], name: str = "Blue Shirt") -> dict:
    response = await async_client.post(
        "/api/v1/closet/",
        headers=headers,
        json={"name": name, "category": "tops", "color": "blue"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_closet_item_returns_201(async_client: AsyncClient, auth_headers: dict[str, str]):
    response = await async_client.post(
        "/api/v1/closet/",
        headers=auth_headers,
        json={"name": "Black Jeans", "category": "bottoms", "color": "black"},
    )

    assert response.status_code == 201
    assert response.json()["id"]
    assert response.json()["name"] == "Black Jeans"


@pytest.mark.asyncio
async def test_get_closet_returns_only_own_items(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "closetusera")
    headers_b = await headers_for(async_client, "closetuserb")
    item_a = await create_item(async_client, headers_a, "Private Shirt")
    await create_item(async_client, headers_b, "Other Shirt")

    response = await async_client.get("/api/v1/closet/", headers=headers_a)

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert item_a["id"] in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_update_closet_item(async_client: AsyncClient, auth_headers: dict[str, str]):
    item = await create_item(async_client, auth_headers)
    response = await async_client.patch(
        f"/api/v1/closet/{item['id']}",
        headers=auth_headers,
        json={"name": "Updated Shirt"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Shirt"


@pytest.mark.asyncio
async def test_delete_closet_item(async_client: AsyncClient, auth_headers: dict[str, str]):
    item = await create_item(async_client, auth_headers)
    delete = await async_client.delete(f"/api/v1/closet/{item['id']}", headers=auth_headers)
    listing = await async_client.get("/api/v1/closet/", headers=auth_headers)

    assert delete.status_code == 204
    assert item["id"] not in {i["id"] for i in listing.json()["items"]}


@pytest.mark.asyncio
async def test_cannot_delete_other_users_item(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "deleteusera")
    headers_b = await headers_for(async_client, "deleteuserb")
    item = await create_item(async_client, headers_a)

    response = await async_client.delete(f"/api/v1/closet/{item['id']}", headers=headers_b)

    assert response.status_code == 404
