"""Regression tests for update_item_embedding_job's commit-visibility race.

The job opens its own session, so a row created/updated by a request is only
visible to it after that request's transaction commits. Call sites commit
before scheduling; the job itself retries briefly (covering the ARQ-worker
variant of the race) and logs a warning instead of silently skipping.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.services import similarity_service

# Bind the real coroutine at import time — conftest's autouse fixture replaces
# the module attribute with a noop for route-level tests, but these tests are
# about the job itself.
_real_job = similarity_service.update_item_embedding_job

ITEM_ID = "00000000-0000-0000-0000-000000000001"


class FakeSession:
    """Minimal async-session stand-in: context manager + get/execute/commit."""

    def __init__(self, item):
        self._item = item
        self.committed = False
        self.rolled_back = False
        self.statements: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        self.statements.append(str(stmt))

    async def get(self, model, pk):
        return self._item

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _install(monkeypatch, sessions: list[FakeSession]) -> list[float]:
    """Wire fakes: pop one session per attempt, record sleeps, stub embedding."""
    queue = list(sessions)
    monkeypatch.setattr(similarity_service, "AsyncSessionLocal", lambda: queue.pop(0))
    monkeypatch.setattr(
        similarity_service, "generate_item_embedding", AsyncMock(return_value=[0.1, 0.2])
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(similarity_service.asyncio, "sleep", fake_sleep)
    return sleeps


async def test_embeds_and_commits_when_row_visible(monkeypatch):
    item = MagicMock()
    session = FakeSession(item)
    sleeps = _install(monkeypatch, [session])

    await _real_job(ITEM_ID)

    assert item.embedding == [0.1, 0.2]
    assert session.committed
    assert sleeps == []  # no retries needed


async def test_sets_lock_timeout_before_touching_the_row(monkeypatch):
    session = FakeSession(MagicMock())
    _install(monkeypatch, [session])

    await _real_job(ITEM_ID)

    assert any("lock_timeout" in s for s in session.statements)


async def test_retries_until_row_becomes_visible(monkeypatch):
    """First attempt races the creating transaction's commit; second succeeds."""
    item = MagicMock()
    first, second = FakeSession(None), FakeSession(item)
    sleeps = _install(monkeypatch, [first, second])

    await _real_job(ITEM_ID)

    assert item.embedding == [0.1, 0.2]
    assert second.committed
    assert sleeps == [0.5]


async def test_gives_up_quietly_when_row_never_appears(monkeypatch):
    sessions = [FakeSession(None) for _ in range(3)]
    sleeps = _install(monkeypatch, sessions)

    # Must not raise — deleted items (or a rolled-back create) are expected.
    await _real_job(ITEM_ID)

    assert not any(s.committed for s in sessions)
    assert len(sleeps) == 3
