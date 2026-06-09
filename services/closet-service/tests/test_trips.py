"""Trip CRUD + packing-plan persistence + date validation + isolation.

POST /trips runs AI packing generation (ai-agent / packing_service). That call is
stubbed here so the tests are deterministic and offline; embeddings are already
neutralised globally in conftest.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

import app.api.v1.trips as trips_mod

_START = (date.today() + timedelta(days=10)).isoformat()
_END = (date.today() + timedelta(days=14)).isoformat()

TRIP = {"destination": "Lisbon", "start_date": _START, "end_date": _END, "purpose": "leisure"}


@pytest.fixture(autouse=True)
def stub_packing(monkeypatch):
    """Replace AI packing generation so trip creation is offline + deterministic."""

    async def fake_packing(*_a, **_kw) -> dict[str, Any]:
        return {
            "take_from_your_closet": [],
            "you_might_still_need": [{"name": "Travel adapter", "category": "accessories", "reason": "fixture"}],
            "daily_plan": [],
            "weather_summary": None,
            "summary": "Fixture packing plan.",
        }

    monkeypatch.setattr(trips_mod, "_generate_trip_packing", fake_packing, raising=False)


async def _create_trip(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    resp = await client.post("/api/v1/trips/", json={**TRIP, **overrides}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Auth ────────────────────────────────────────────────────────────────────

async def test_list_trips_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/trips/")
    assert resp.status_code == 401


async def test_empty_trips_list(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/trips/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["trips"] == []


# ── Create + read ─────────────────────────────────────────────────────────────

async def test_create_trip_returns_201(client: AsyncClient, auth_headers, user_id) -> None:
    body = await _create_trip(client, auth_headers)
    assert body["trip"]["destination"] == "Lisbon"
    assert body["trip"]["purpose"] == "leisure"
    assert body["trip"]["user_id"] == user_id
    # Packing plan came from the stub, no AI error surfaced.
    assert body["packing_error"] is None


async def test_created_trip_in_list_and_detail(client: AsyncClient, auth_headers) -> None:
    created = await _create_trip(client, auth_headers)
    trip_id = created["trip"]["id"]

    listing = await client.get("/api/v1/trips/", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    detail = await client.get(f"/api/v1/trips/{trip_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == trip_id


# ── Validation ────────────────────────────────────────────────────────────────

async def test_end_before_start_rejected(client: AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/trips/",
        json={**TRIP, "start_date": _END, "end_date": _START},  # end < start
        headers=auth_headers,
    )
    assert resp.status_code == 422  # schema model_validator


async def test_invalid_purpose_rejected(client: AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/trips/", json={**TRIP, "purpose": "moon-landing"}, headers=auth_headers
    )
    assert resp.status_code == 422


# ── Delete + isolation ────────────────────────────────────────────────────────

async def test_delete_trip(client: AsyncClient, auth_headers) -> None:
    created = await _create_trip(client, auth_headers)
    trip_id = created["trip"]["id"]
    resp = await client.delete(f"/api/v1/trips/{trip_id}", headers=auth_headers)
    assert resp.status_code == 204
    follow = await client.get(f"/api/v1/trips/{trip_id}", headers=auth_headers)
    assert follow.status_code == 404


async def test_trips_are_user_scoped(client: AsyncClient, auth_headers, other_user_headers) -> None:
    await _create_trip(client, auth_headers)
    resp = await client.get("/api/v1/trips/", headers=other_user_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_other_user_cannot_get_trip(client: AsyncClient, auth_headers, other_user_headers) -> None:
    created = await _create_trip(client, auth_headers)
    trip_id = created["trip"]["id"]
    resp = await client.get(f"/api/v1/trips/{trip_id}", headers=other_user_headers)
    assert resp.status_code == 404
