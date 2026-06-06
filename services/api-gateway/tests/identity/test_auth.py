"""Unit tests for auth endpoints and username generation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.username import generate_unique_username, normalize_username


# ── Existing baseline tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "Test User",
        "email": "test@example.com",
        "username": "testuser",
        "password": "Password1",
        "gdpr_consent": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["username"] == "testuser"
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    payload = {
        "name": "Dup User",
        "email": "dup@example.com",
        "username": "dupuser",
        "password": "Password1",
        "gdpr_consent": True,
    }
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post("/api/v1/auth/signup", json={**payload, "username": "dupuser2"})
    assert resp.status_code == 409
    body = resp.json()
    assert "Email" in body.get("detail", "") or "Email" in body.get("message", "")


@pytest.mark.asyncio
async def test_signup_weak_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "Weak",
        "email": "weak@example.com",
        "username": "weakuser",
        "password": "password",  # no uppercase, no digit
        "gdpr_consent": True,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_health_live(client: AsyncClient):
    resp = await client.get("/live")
    assert resp.status_code == 200
    assert resp.json().get("status") == "alive"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json={
        "name": "Login Test",
        "email": "logintest@example.com",
        "username": "logintest",
        "password": "Password1",
        "gdpr_consent": True,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "identifier": "logintest@example.com",
        "password": "Password1",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json={
        "name": "Wrong Pass",
        "email": "wrongpass@example.com",
        "username": "wrongpass",
        "password": "Password1",
        "gdpr_consent": True,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "identifier": "wrongpass@example.com",
        "password": "WrongPass1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient):
    signup = await client.post("/api/v1/auth/signup", json={
        "name": "Me Test",
        "email": "metest@example.com",
        "username": "metest",
        "password": "Password1",
        "gdpr_consent": True,
    })
    token = signup.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "metest@example.com"


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    signup = await client.post("/api/v1/auth/signup", json={
        "name": "Refresh Test",
        "email": "refresh@example.com",
        "username": "refreshtest",
        "password": "Password1",
        "gdpr_consent": True,
    })
    refresh_token = signup.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token  # token rotated


# ── Task 12: new profile-name tests ───────────────────────────────────────────

class TestNormalizeUsername:
    """Unit tests for the normalize_username helper."""

    def test_spaces_removed(self):
        assert normalize_username("Phanidhar Reddy") == "phanidharreddy"

    def test_multi_word(self):
        assert normalize_username("John Smith") == "johnsmith"

    def test_already_lowercase(self):
        assert normalize_username("alice") == "alice"

    def test_special_chars_stripped(self):
        assert normalize_username("phani@gmail") == "phanigmail"

    def test_underscores_preserved(self):
        assert normalize_username("john_smith") == "john_smith"

    def test_empty_string_fallback(self):
        assert normalize_username("") == "user"

    def test_only_special_chars_fallback(self):
        assert normalize_username("!@#$%") == "user"

    def test_truncation(self):
        long_name = "a" * 50
        assert len(normalize_username(long_name)) == 30

    def test_email_prefix(self):
        assert normalize_username("phani") == "phani"


# ── Task 12.1: local signup generates username ────────────────────────────────

@pytest.mark.asyncio
async def test_signup_auto_generates_username_from_name(client: AsyncClient):
    """When no username is provided, one is generated from the name."""
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "Phanidhar Reddy",
        "email": "phanidhar@example.com",
        "password": "Password1",
        "gdpr_consent": True,
        # no username field
    })
    assert resp.status_code == 201
    user = resp.json()["user"]
    assert user["username"] == "phanidharreddy"


@pytest.mark.asyncio
async def test_signup_auto_generates_username_from_email_when_name_empty(client: AsyncClient):
    """Name of single word falls back cleanly; pure email prefix is used."""
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "Phani",
        "email": "phaniuser@example.com",
        "password": "Password1",
        "gdpr_consent": True,
    })
    assert resp.status_code == 201
    assert resp.json()["user"]["username"] == "phani"


@pytest.mark.asyncio
async def test_signup_response_contains_username(client: AsyncClient):
    """Login response always includes username."""
    await client.post("/api/v1/auth/signup", json={
        "name": "Alice B",
        "email": "alice@example.com",
        "username": "aliceb",
        "password": "Password1",
        "gdpr_consent": True,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "identifier": "alice@example.com",
        "password": "Password1",
    })
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["username"] == "aliceb"
    assert user["display_name"] == "Alice B"


# ── Task 12.2: duplicate username rejected ────────────────────────────────────

@pytest.mark.asyncio
async def test_signup_rejects_duplicate_username(client: AsyncClient):
    """Requesting an already-taken username returns 409."""
    await client.post("/api/v1/auth/signup", json={
        "name": "User One",
        "email": "user1@example.com",
        "username": "sharedname",
        "password": "Password1",
        "gdpr_consent": True,
    })
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "User Two",
        "email": "user2@example.com",
        "username": "sharedname",
        "password": "Password1",
        "gdpr_consent": True,
    })
    assert resp.status_code == 409
    assert "taken" in resp.json().get("detail", "").lower()


# ── Task 12.6: numeric suffix for duplicate generated usernames ───────────────

@pytest.mark.asyncio
async def test_auto_username_gets_numeric_suffix_on_collision(client: AsyncClient):
    """Two users with the same name get phani and phani1."""
    resp1 = await client.post("/api/v1/auth/signup", json={
        "name": "Phani",
        "email": "phani1@example.com",
        "password": "Password1",
        "gdpr_consent": True,
    })
    resp2 = await client.post("/api/v1/auth/signup", json={
        "name": "Phani",
        "email": "phani2@example.com",
        "password": "Password1",
        "gdpr_consent": True,
    })
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    u1 = resp1.json()["user"]["username"]
    u2 = resp2.json()["user"]["username"]
    assert u1 != u2
    assert u2 == f"{u1}1"


# ── Task 12.7: /auth/me returns username ─────────────────────────────────────

@pytest.mark.asyncio
async def test_me_returns_username_and_display_name(client: AsyncClient):
    signup = await client.post("/api/v1/auth/signup", json={
        "name": "Profile Check",
        "email": "profilecheck@example.com",
        "username": "profilecheck",
        "password": "Password1",
        "gdpr_consent": True,
    })
    token = signup.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    user = resp.json()
    assert user["username"] == "profilecheck"
    assert user["display_name"] == "Profile Check"
    assert user["name"] == "Profile Check"


# ── Task 12.8 & 12.9: profile update username rules ──────────────────────────

@pytest.mark.asyncio
async def test_update_username_rejects_duplicate(client: AsyncClient):
    """PATCH /auth/me returns 409 when the requested username is already taken."""
    await client.post("/api/v1/auth/signup", json={
        "name": "Owner",
        "email": "owner@example.com",
        "username": "takenname",
        "password": "Password1",
        "gdpr_consent": True,
    })
    signup2 = await client.post("/api/v1/auth/signup", json={
        "name": "Other",
        "email": "other@example.com",
        "username": "othername",
        "password": "Password1",
        "gdpr_consent": True,
    })
    token = signup2.json()["access_token"]

    resp = await client.patch(
        "/api/v1/auth/me",
        json={"username": "takenname"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_username_success(client: AsyncClient):
    """PATCH /auth/me successfully changes a username."""
    signup = await client.post("/api/v1/auth/signup", json={
        "name": "Chang Me",
        "email": "changeme@example.com",
        "username": "oldname",
        "password": "Password1",
        "gdpr_consent": True,
    })
    token = signup.json()["access_token"]

    resp = await client.patch(
        "/api/v1/auth/me",
        json={"username": "newname"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "newname"


# ── Task 12.7 (generate_unique_username unit) ─────────────────────────────────

@pytest.mark.asyncio
async def test_generate_unique_username_unit(db_session: AsyncSession):
    """generate_unique_username returns a non-empty unique slug."""
    u = await generate_unique_username(db_session, "Phanidhar Reddy", "phani@gmail.com")
    assert u == "phanidharreddy"


@pytest.mark.asyncio
async def test_generate_unique_username_email_fallback(db_session: AsyncSession):
    """Empty base_name falls back to email prefix."""
    u = await generate_unique_username(db_session, "", "phani@gmail.com")
    assert u == "phani"


@pytest.mark.asyncio
async def test_generate_unique_username_collision(client: AsyncClient, db_session: AsyncSession):
    """After 'phani' exists, next call gets 'phani1'."""
    await client.post("/api/v1/auth/signup", json={
        "name": "Phani",
        "email": "phani.col@example.com",
        "password": "Password1",
        "gdpr_consent": True,
    })
    u = await generate_unique_username(db_session, "Phani", "other@example.com")
    assert u == "phani1"
