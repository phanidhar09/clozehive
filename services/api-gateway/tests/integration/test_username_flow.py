"""Integration tests for username system and auth_provider field."""
import pytest
from httpx import AsyncClient


def _payload(prefix: str) -> dict:
    return {
        "name": f"{prefix} Test",
        "email": f"{prefix}@example.com",
        "username": f"{prefix}user",
        "password": "Password1",
    }


# ── auth_provider ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signup_sets_auth_provider_local(async_client: AsyncClient):
    """Email/password signup must set auth_provider='local'."""
    resp = await async_client.post("/api/v1/auth/register", json=_payload("provlocal"))
    assert resp.status_code == 201
    user = resp.json()["user"]
    assert user["auth_provider"] == "local"


@pytest.mark.asyncio
async def test_login_returns_auth_provider(async_client: AsyncClient):
    """Login response includes auth_provider."""
    payload = _payload("loginprov")
    await async_client.post("/api/v1/auth/register", json=payload)
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": payload["email"], "password": payload["password"]},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["auth_provider"] == "local"


# ── GET /me ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_returns_username_and_auth_provider(async_client: AsyncClient):
    """GET /me returns username and auth_provider."""
    payload = _payload("mecheck")
    reg = await async_client.post("/api/v1/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "mecheckuser"
    assert data["auth_provider"] == "local"


# ── PATCH /me username update ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_me_updates_username(async_client: AsyncClient):
    """PATCH /me allows a user to change their username."""
    payload = _payload("patchuser")
    reg = await async_client.post("/api/v1/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await async_client.patch(
        "/api/v1/auth/me",
        json={"username": "newpatchname"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "newpatchname"


@pytest.mark.asyncio
async def test_patch_me_username_conflict_returns_409(async_client: AsyncClient):
    """PATCH /me rejects a username already taken by another user."""
    # Register user A
    p_a = _payload("conflicta")
    await async_client.post("/api/v1/auth/register", json=p_a)

    # Register user B and try to take user A's username
    p_b = _payload("conflictb")
    reg_b = await async_client.post("/api/v1/auth/register", json=p_b)
    token_b = reg_b.json()["access_token"]

    resp = await async_client.patch(
        "/api/v1/auth/me",
        json={"username": p_a["username"]},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_patch_me_same_username_is_ok(async_client: AsyncClient):
    """PATCH /me with the user's own username should succeed (no self-conflict)."""
    payload = _payload("sameusername")
    reg = await async_client.post("/api/v1/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await async_client.patch(
        "/api/v1/auth/me",
        json={"username": payload["username"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == payload["username"]


@pytest.mark.asyncio
async def test_patch_me_invalid_username_returns_422(async_client: AsyncClient):
    """PATCH /me rejects usernames containing invalid characters."""
    payload = _payload("invalid_uname")
    reg = await async_client.post("/api/v1/auth/register", json=payload)
    token = reg.json()["access_token"]

    resp = await async_client.patch(
        "/api/v1/auth/me",
        json={"username": "bad name!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
