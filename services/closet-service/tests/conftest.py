"""Pytest configuration and shared fixtures for closet-service.

Integration tests run against SQLite in-memory + fakes, so **no Postgres, Redis,
OpenAI, GCS, or weather credentials** are required.

Key difference from api-gateway tests: closet-service has no ``/auth`` endpoints —
it authenticates by validating the gateway-issued JWT locally with the shared
secret. So the ``auth_headers`` fixture mints a token directly via
``app.core.security.create_access_token`` (signed with whatever ``JWT_SECRET`` the
app loaded), and no ``users`` row is needed because ``get_current_user_id`` simply
returns the ``sub`` claim.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

# Ensure the app loads with a deterministic dev config even if the repo .env is
# absent (CI). Set before importing app.* so Settings picks these up.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-32-chars-long-xx")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.api.v1.closet as closet_mod
import app.core.redis as redis_core
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.services import cache_service, similarity_service

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


class FakeRedis:
    """Minimal async Redis stand-in covering the calls closet-service makes."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.data[key] = value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self.data.pop(str(k), None)

    async def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    async def ping(self) -> bool:
        return True

    async def scan_iter(self, match=None, count=None):
        for key in list(self.data):
            yield key

    async def close(self) -> None:
        return None


def _patch_postgres_types_for_sqlite() -> None:
    """Make PostgreSQL-specific DDL compile under SQLite.

      1. ``ARRAY`` / ``JSONB`` / pgvector ``Vector`` columns → portable ``JSON``.
      2. ``::type`` casts inside ``server_default`` (e.g. ``'[]'::jsonb``) → SQLite
         can't parse them, so strip the cast and keep the plain literal.
    """
    import re as _re

    for table in Base.metadata.tables.values():
        for col in table.columns:
            type_name = type(col.type).__name__
            if isinstance(col.type, (ARRAY, JSONB)) or type_name == "Vector":
                col.type = JSON()
            sd = col.server_default
            arg = getattr(sd, "arg", None)
            sql_text = getattr(arg, "text", None)
            if isinstance(sql_text, str) and "::" in sql_text:
                arg.text = _re.sub(r"::\w+", "", sql_text)


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    """Swap Redis, embeddings, and WebSocket pushes for in-process fakes."""
    fake_redis = FakeRedis()
    cache_store: dict[str, Any] = {}

    async def get_fake_redis() -> FakeRedis:
        return fake_redis

    async def mem_cache_get(key: str) -> Any | None:
        return cache_store.get(key)

    async def mem_cache_set(key: str, value: Any, _ttl: int) -> bool:
        cache_store[key] = value
        return True

    async def mem_cache_delete(key: str) -> None:
        cache_store.pop(key, None)

    async def ok() -> bool:
        return True

    # Redis accessors are imported in different modules — patch wherever present.
    for target in (redis_core, cache_service, closet_mod):
        if hasattr(target, "get_redis"):
            monkeypatch.setattr(target, "get_redis", get_fake_redis)
        if hasattr(target, "get_state_redis"):
            monkeypatch.setattr(target, "get_state_redis", get_fake_redis)

    monkeypatch.setattr(cache_service, "get", mem_cache_get, raising=False)
    monkeypatch.setattr(cache_service, "set", mem_cache_set, raising=False)
    monkeypatch.setattr(cache_service, "delete", mem_cache_delete, raising=False)
    monkeypatch.setattr(cache_service, "ping", ok, raising=False)

    limiter.enabled = False

    # Embedding generation calls OpenAI — no-op it in both the request path and
    # the post-response background job.
    async def noop_embedding(*_a, **_kw):
        return None

    monkeypatch.setattr(similarity_service, "update_item_embedding_in_request", noop_embedding, raising=False)
    monkeypatch.setattr(similarity_service, "update_item_embedding_job", noop_embedding, raising=False)

    # generate_text_embedding hits the OpenAI API. It's imported by value into
    # many service modules, so patch every binding (and the source) → None, which
    # all callers treat as "embedding unavailable" and skip gracefully. Without
    # this, RAG/packing paths make real network calls and tests crawl.
    import importlib

    async def noop_text_embedding(*_a, **_kw):
        return None

    _embedding_importers = (
        "app.services.embedding_service",
        "app.services.packing_memory_service",
        "app.services.fashion_rag_service",
        "app.services.outfit_history_service",
        "app.services.closet_similarity_service",
        "app.services.shopping_check_service",
        "app.services.ai_stylist_streaming",
        "app.services.ai_stylist_chat_service",
        "app.services.trend_ingest_service",
        "app.rag.retriever",
    )
    for mod_path in _embedding_importers:
        try:
            mod = importlib.import_module(mod_path)
        except Exception:
            continue
        if hasattr(mod, "generate_text_embedding"):
            monkeypatch.setattr(mod, "generate_text_embedding", noop_text_embedding, raising=False)

    # WebSocket push fires a background task that would touch Redis pub/sub.
    monkeypatch.setattr(closet_mod, "_ws_push", lambda *_a, **_kw: None, raising=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    _patch_postgres_types_for_sqlite()
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
async def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        yield c


@pytest.fixture
def user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def auth_headers(user_id: str) -> dict[str, str]:
    """A bearer token for ``user_id`` signed with the app's JWT secret."""
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.fixture
def other_user_headers() -> dict[str, str]:
    """A bearer token for a *different* user, for cross-user isolation tests."""
    return {"Authorization": f"Bearer {create_access_token(str(uuid.uuid4()))}"}
