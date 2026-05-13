"""Pytest configuration and shared integration fixtures.

Integration tests use SQLite in-memory + fakes so **no Postgres, Redis, OpenAI,
GCS, or weather credentials** are required. See Readme.md (Testing) for commands.

- **Redis**: in-memory ``FakeRedis`` for rate-limit / auth token storage.
- **cache_service**: in-memory dict so closet **analyze-preview** sessions work.
- **ai_client.generate_packing_list**: deterministic fixture (trip packing without HTTP to ai-agent).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

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
from app.services import auth_service, ai_client, cache_service
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


async def _deterministic_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None = None,
    user_style_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Stub ai-agent packing: echoes real closet item ids/names so trip tests
    prove packing uses the user's wardrobe (no HTTP, no OpenAI/weather).
    """
    take: list[dict[str, Any]] = []
    for it in closet_items[:20]:
        take.append(
            {
                "item_id": it.get("id"),
                "name": str(it.get("name") or ""),
                "category": str(it.get("category") or "general"),
                "reason": "Fixture: packed from your closet.",
                "recommended_days": [],
            }
        )
    return {
        "take_from_your_closet": take,
        "you_might_still_need": [{"name": "Travel adapter", "category": "accessories", "reason": "Fixture"}],
        "daily_plan": [],
        "weather_summary": None,
        "summary": f"Test packing for {destination} ({purpose}).",
    }


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    fake_redis = FakeRedis()
    cache_store: dict[str, Any] = {}

    async def get_fake_redis() -> FakeRedis:
        return fake_redis

    async def noop(*_args, **_kwargs):
        return None

    async def ok():
        return True

    async def mem_cache_get(key: str) -> Any | None:
        return cache_store.get(key)

    async def mem_cache_set(key: str, value: Any, _ttl: int) -> bool:
        cache_store[key] = value
        return True

    async def mem_cache_delete(key: str) -> None:
        cache_store.pop(key, None)

    monkeypatch.setattr(redis_core, "get_redis", get_fake_redis)
    monkeypatch.setattr(auth_service, "get_redis", get_fake_redis)
    monkeypatch.setattr(ai_mod, "get_redis", get_fake_redis)
    monkeypatch.setattr(closet_mod, "get_redis", get_fake_redis)
    monkeypatch.setattr(cache_service, "get_redis", get_fake_redis)
    monkeypatch.setattr(cache_service, "get", mem_cache_get)
    monkeypatch.setattr(cache_service, "set", mem_cache_set)
    monkeypatch.setattr(cache_service, "delete", mem_cache_delete)
    monkeypatch.setattr(cache_service, "ping", ok)
    limiter.enabled = False

    monkeypatch.setattr(ai_client, "generate_packing_list", _deterministic_packing_list)

    async def noop_embedding(*_a, **_kw):
        return None

    monkeypatch.setattr(
        "app.services.similarity_service.update_item_embedding_in_request",
        noop_embedding,
    )
    monkeypatch.setattr(
        "app.services.similarity_service.update_item_embedding_job",
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
