"""Unit tests for auth endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "Test User",
        "email": "test@example.com",
        "username": "testuser",
        "password": "Password1",
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
    }
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post("/api/v1/auth/signup", json={**payload, "username": "dupuser2"})
    assert resp.status_code == 409
    assert "Email" in resp.json()["message"]


@pytest.mark.asyncio
async def test_signup_weak_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "name": "Weak",
        "email": "weak@example.com",
        "username": "weakuser",
        "password": "password",  # no uppercase, no digit
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    # First create account
    await client.post("/api/v1/auth/signup", json={
        "name": "Login Test",
        "email": "logintest@example.com",
        "username": "logintest",
        "password": "Password1",
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
    })
    refresh_token = signup.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token  # token rotated


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")
