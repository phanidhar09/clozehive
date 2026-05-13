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
    """Returns the ``trip`` object from :class:`CreateTripResponse` JSON."""
    response = await async_client.post("/api/v1/trips/", headers=headers, json=trip_payload(destination))
    assert response.status_code == 201
    return response.json()["trip"]


async def create_trip_response(async_client: AsyncClient, headers: dict[str, str]) -> dict:
    """Full POST /trips/ body (``trip``, ``packing_plan``, ``packing_error``)."""
    response = await async_client.post("/api/v1/trips/", headers=headers, json=trip_payload())
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_trip_returns_201(async_client: AsyncClient, auth_headers: dict[str, str]):
    response = await async_client.post("/api/v1/trips/", headers=auth_headers, json=trip_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["trip"]["id"]
    assert body.get("packing_plan") is not None


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


@pytest.mark.asyncio
async def test_trip_has_is_saved_false_by_default(async_client: AsyncClient, auth_headers: dict[str, str]):
    response = await async_client.post("/api/v1/trips/", headers=auth_headers, json=trip_payload())
    assert response.status_code == 201
    data = response.json()
    assert data["trip"]["is_saved"] is False


@pytest.mark.asyncio
async def test_save_planner_requires_packing_plan(
    async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
):
    """save-planner returns 404 when no packing plan row exists for the trip."""

    async def _fail_packing(*_a, **_kw):
        raise RuntimeError("forced packing failure for test")

    monkeypatch.setattr("app.api.v1.trips._generate_trip_packing", _fail_packing)

    response = await async_client.post("/api/v1/trips/", headers=auth_headers, json=trip_payload())
    assert response.status_code == 201
    data = response.json()
    assert data.get("packing_plan") is None
    trip_id = data["trip"]["id"]

    save = await async_client.post(f"/api/v1/trips/{trip_id}/save-planner", headers=auth_headers)
    assert save.status_code == 404


@pytest.mark.asyncio
async def test_list_saved_trips_only_returns_saved(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "savedusera")
    trip_data = await create_trip_response(async_client, headers_a)
    trip_id = trip_data["trip"]["id"]

    saved_before = await async_client.get("/api/v1/trips/saved", headers=headers_a)
    assert saved_before.status_code == 200
    assert saved_before.json()["total"] == 0

    assert trip_data.get("packing_plan") is not None
    save = await async_client.post(f"/api/v1/trips/{trip_id}/save-planner", headers=headers_a)
    assert save.status_code == 200
    assert save.json()["trip"]["is_saved"] is True
    assert save.json()["packing_plan"]["is_saved"] is True

    saved_after = await async_client.get("/api/v1/trips/saved", headers=headers_a)
    assert saved_after.status_code == 200
    assert saved_after.json()["total"] == 1
    assert saved_after.json()["trips"][0]["id"] == trip_id


@pytest.mark.asyncio
async def test_save_planner_is_idempotent(async_client: AsyncClient):
    headers = await headers_for(async_client, "idempotentuser")
    data = await create_trip_response(async_client, headers)
    assert data.get("packing_plan") is not None
    trip_id = data["trip"]["id"]
    save1 = await async_client.post(f"/api/v1/trips/{trip_id}/save-planner", headers=headers)
    save2 = await async_client.post(f"/api/v1/trips/{trip_id}/save-planner", headers=headers)
    assert save1.status_code == 200
    assert save2.status_code == 200
    assert save2.json()["trip"]["is_saved"] is True

    saved = await async_client.get("/api/v1/trips/saved", headers=headers)
    assert saved.json()["total"] == 1


@pytest.mark.asyncio
async def test_cannot_save_other_users_planner(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "plannerownera")
    headers_b = await headers_for(async_client, "plannerownerb")
    trip_data = await create_trip_response(async_client, headers_a)
    trip_id = trip_data["trip"]["id"]

    response = await async_client.post(f"/api/v1/trips/{trip_id}/save-planner", headers=headers_b)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_trip_returns_detail(async_client: AsyncClient, auth_headers: dict[str, str]):
    created = await create_trip(async_client, auth_headers)
    res = await async_client.get(f"/api/v1/trips/{created['id']}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]
    assert res.json()["destination"] == "Paris"


@pytest.mark.asyncio
async def test_update_trip(async_client: AsyncClient, auth_headers: dict[str, str]):
    created = await create_trip(async_client, auth_headers)
    new_payload = trip_payload("Tokyo")
    res = await async_client.patch(
        f"/api/v1/trips/{created['id']}",
        headers=auth_headers,
        json=new_payload,
    )
    assert res.status_code == 200
    assert res.json()["destination"] == "Tokyo"


@pytest.mark.asyncio
async def test_packing_plan_reflects_user_closet_items(async_client: AsyncClient):
    """Packing ``take_from_your_closet`` includes items the user actually owns."""
    headers = await headers_for(async_client, "packingclosetuser")
    distinctive = "MVP-Regression-Denim-001"
    create_item = await async_client.post(
        "/api/v1/closet/",
        headers=headers,
        json={"name": distinctive, "category": "bottoms", "color": "indigo"},
    )
    assert create_item.status_code == 201

    trip_data = await create_trip_response(async_client, headers)
    plan = trip_data["packing_plan"]
    assert plan is not None
    take = plan.get("take_from_your_closet") or []
    names = {str(x.get("name") or "") for x in take}
    assert distinctive in names


@pytest.mark.asyncio
async def test_get_packing_plan_after_save(async_client: AsyncClient):
    """GET /trips/{id}/packing-plan returns the stored plan after save-planner."""
    headers = await headers_for(async_client, "packingpersistuser")
    trip_data = await create_trip_response(async_client, headers)
    trip_id = trip_data["trip"]["id"]
    assert trip_data.get("packing_plan")

    save = await async_client.post(f"/api/v1/trips/{trip_id}/save-planner", headers=headers)
    assert save.status_code == 200

    persisted = await async_client.get(f"/api/v1/trips/{trip_id}/packing-plan", headers=headers)
    assert persisted.status_code == 200
    body = persisted.json()
    assert str(body.get("trip_id")) == str(trip_id)
    assert body.get("is_saved") is True
