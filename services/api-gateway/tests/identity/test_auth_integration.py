import pytest
from httpx import AsyncClient


def user_payload(prefix: str) -> dict:
    return {
        "name": f"{prefix} User",
        "email": f"{prefix}@example.com",
        "username": f"{prefix}user",
        "password": "Password1",
        "gdpr_consent": True,
    }


@pytest.mark.asyncio
async def test_register_new_user_returns_201(async_client: AsyncClient):
    response = await async_client.post("/api/v1/auth/register", json=user_payload("registernew"))

    assert response.status_code == 201
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(async_client: AsyncClient):
    payload = user_payload("duplicate")
    await async_client.post("/api/v1/auth/register", json=payload)
    response = await async_client.post(
        "/api/v1/auth/register",
        json={**payload, "username": "duplicateuser2"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_tokens(async_client: AsyncClient):
    payload = user_payload("loginvalid")
    await async_client.post("/api/v1/auth/register", json=payload)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": payload["email"], "password": payload["password"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user" in data


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(async_client: AsyncClient):
    payload = user_payload("wrongpassword")
    await async_client.post("/api/v1/auth/register", json=payload)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": payload["email"], "password": "WrongPassword1"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_returns_new_access_token(async_client: AsyncClient):
    payload = user_payload("refreshvalid")
    register = await async_client.post("/api/v1/auth/register", json=payload)
    original_access = register.json()["access_token"]
    refresh_token = register.json()["refresh_token"]

    response = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"] != original_access


@pytest.mark.asyncio
async def test_logout_invalidates_refresh_token(async_client: AsyncClient):
    payload = user_payload("logoutvalid")
    register = await async_client.post("/api/v1/auth/register", json=payload)
    refresh_token = register.json()["refresh_token"]

    logout = await async_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    response = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert logout.status_code == 200
    assert response.status_code == 401
