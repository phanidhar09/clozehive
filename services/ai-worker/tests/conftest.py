"""Shared fixtures for ai-worker tests — no Redis, no Postgres, no HTTP.

All Settings fields have defaults, so no env vars are required. Task tests
monkeypatch the db / client / metrics collaborators in app.worker's namespace.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.worker as worker


@pytest.fixture
def fake_db(monkeypatch) -> AsyncMock:
    """Replace the asyncpg-backed db module with an AsyncMock."""
    db = AsyncMock()
    db.request_age_seconds.return_value = 1.5
    monkeypatch.setattr(worker, "db", db)
    return db


@pytest.fixture
def fake_agent(monkeypatch) -> AsyncMock:
    agent = AsyncMock()
    monkeypatch.setattr(worker, "ai_agent_client", agent)
    return agent


@pytest.fixture
def fake_gateway(monkeypatch) -> AsyncMock:
    gateway = AsyncMock()
    monkeypatch.setattr(worker, "gateway_client", gateway)
    return gateway


@pytest.fixture
def recorded_metrics(monkeypatch) -> list[tuple[str, str, float]]:
    calls: list[tuple[str, str, float]] = []
    monkeypatch.setattr(
        worker, "record_job_terminal", lambda task, status, age: calls.append((task, status, age))
    )
    return calls
