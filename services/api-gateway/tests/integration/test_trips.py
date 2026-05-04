from datetime import date, timedelta

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


def trip_payload(destination: str = "Paris") -> dict:
    start = date.today() + timedelta(days=30)
    end = start + timedelta(days=4)
    return {
        "destination": destination,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "purpose": "leisure",
    }


async def create_trip(async_client: AsyncClient, headers: dict[str, str], destination: str = "Paris") -> dict:
    response = await async_client.post("/api/v1/trips/", headers=headers, json=trip_payload(destination))
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_trip_returns_201(async_client: AsyncClient, auth_headers: dict[str, str]):
    response = await async_client.post("/api/v1/trips/", headers=auth_headers, json=trip_payload())

    assert response.status_code == 201
    assert response.json()["id"]


@pytest.mark.asyncio
async def test_end_date_before_start_date_returns_400(async_client: AsyncClient, auth_headers: dict[str, str]):
    start = date.today() + timedelta(days=10)
    response = await async_client.post(
        "/api/v1/trips/",
        headers=auth_headers,
        json={
            "destination": "Paris",
            "start_date": start.isoformat(),
            "end_date": (start - timedelta(days=1)).isoformat(),
            "purpose": "leisure",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_trips_returns_own_trips_only(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "tripusera")
    headers_b = await headers_for(async_client, "tripuserb")
    trip_a = await create_trip(async_client, headers_a, "Paris")
    await create_trip(async_client, headers_b, "London")

    response = await async_client.get("/api/v1/trips/", headers=headers_a)

    assert response.status_code == 200
    ids = {trip["id"] for trip in response.json()["trips"]}
    assert ids == {trip_a["id"]}


@pytest.mark.asyncio
async def test_delete_trip_removes_from_list(async_client: AsyncClient, auth_headers: dict[str, str]):
    trip = await create_trip(async_client, auth_headers)
    delete = await async_client.delete(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    listing = await async_client.get("/api/v1/trips/", headers=auth_headers)

    assert delete.status_code == 204
    assert trip["id"] not in {t["id"] for t in listing.json()["trips"]}


@pytest.mark.asyncio
async def test_cannot_access_other_users_trip(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "accessusera")
    headers_b = await headers_for(async_client, "accessuserb")
    trip = await create_trip(async_client, headers_a)

    response = await async_client.get(f"/api/v1/trips/{trip['id']}", headers=headers_b)

    assert response.status_code == 404
