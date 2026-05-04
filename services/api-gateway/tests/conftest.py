"""Pytest configuration and shared integration fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.core.rate_limit import limiter
from app.services import auth_service, cache_service
from app.core import redis as redis_core
import app.api.v1.ai as ai_mod
import app.api.v1.closet as closet_mod

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.data[key] = value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, key: str) -> None:
        self.data.pop(str(key), None)

    async def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    async def ping(self) -> bool:
        return True

    async def scan_iter(self, match=None, count=None):
        if False:
            yield ""


def _patch_postgres_arrays_for_sqlite() -> None:
    """SQLite cannot compile PostgreSQL ARRAY, so list columns are JSON in tests."""
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, ARRAY):
                col.type = JSON()
            if isinstance(col.type, JSONB):
                col.type = JSON()


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    fake_redis = FakeRedis()

    async def get_fake_redis() -> FakeRedis:
        return fake_redis

    async def noop(*_args, **_kwargs):
        return None

    async def ok():
        return True

    monkeypatch.setattr(redis_core, "get_redis", get_fake_redis)
    monkeypatch.setattr(auth_service, "get_redis", get_fake_redis)
    monkeypatch.setattr(ai_mod, "get_redis", get_fake_redis)
    monkeypatch.setattr(closet_mod, "get_redis", get_fake_redis)
    monkeypatch.setattr(cache_service, "get_redis", get_fake_redis)
    monkeypatch.setattr(cache_service, "get", noop)
    monkeypatch.setattr(cache_service, "set", noop)
    monkeypatch.setattr(cache_service, "delete", noop)
    monkeypatch.setattr(cache_service, "ping", ok)
    limiter.enabled = False

    async def noop_embedding(*_a, **_kw):
        return None

    monkeypatch.setattr(
        "app.services.similarity_service.update_item_embedding",
        noop_embedding,
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    _patch_postgres_arrays_for_sqlite()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_app(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def client(async_client: AsyncClient) -> AsyncClient:
    return async_client


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Fixture User",
            "email": "fixture@example.com",
            "username": "fixtureuser",
            "password": "Password1",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
