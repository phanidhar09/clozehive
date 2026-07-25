"""Tests for the heavy_work_async transport switch in schedule_embedding_update.

The scheduler picks between the durable ARQ queue and an in-process
BackgroundTask based on ``settings.heavy_work_async``, and falls back to
in-process if the queue is unreachable so work is never dropped.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api.v1.wardrobe.services import similarity_service

ITEM_ID = "00000000-0000-0000-0000-000000000042"


class FakeBackgroundTasks:
    """Records add_task calls the way FastAPI's BackgroundTasks would receive them."""

    def __init__(self) -> None:
        self.tasks: list[tuple] = []

    def add_task(self, func, *args, **kwargs) -> None:
        self.tasks.append((func, args, kwargs))


@pytest.fixture
def recorded_transports(monkeypatch):
    """Capture record_embedding_job(transport) calls."""
    transports: list[str] = []
    monkeypatch.setattr(
        "app.core.metrics.record_embedding_job",
        lambda transport: transports.append(transport),
    )
    return transports


async def test_inprocess_when_flag_off(monkeypatch, recorded_transports):
    monkeypatch.setattr(similarity_service.settings, "heavy_work_async", False)
    bg = FakeBackgroundTasks()

    await similarity_service.schedule_embedding_update(bg, ITEM_ID)

    assert recorded_transports == ["inprocess"]
    assert len(bg.tasks) == 1
    func, args, _ = bg.tasks[0]
    assert func is similarity_service.update_item_embedding_job
    assert args == (ITEM_ID,)


async def test_enqueues_to_arq_when_flag_on(monkeypatch, recorded_transports):
    monkeypatch.setattr(similarity_service.settings, "heavy_work_async", True)
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr("app.core.task_queue.enqueue_job", enqueue)
    bg = FakeBackgroundTasks()

    await similarity_service.schedule_embedding_update(bg, ITEM_ID)

    enqueue.assert_awaited_once_with("refresh_item_embedding", ITEM_ID)
    assert recorded_transports == ["arq"]
    assert bg.tasks == []  # nothing runs in-process on the web dyno


async def test_falls_back_inprocess_when_enqueue_fails(monkeypatch, recorded_transports):
    monkeypatch.setattr(similarity_service.settings, "heavy_work_async", True)
    monkeypatch.setattr("app.core.task_queue.enqueue_job", AsyncMock(return_value=False))
    bg = FakeBackgroundTasks()

    await similarity_service.schedule_embedding_update(bg, ITEM_ID)

    # Queue unreachable → work still scheduled in-process, not dropped.
    assert recorded_transports == ["inprocess"]
    assert len(bg.tasks) == 1
    assert bg.tasks[0][1] == (ITEM_ID,)
