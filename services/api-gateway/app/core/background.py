"""
Fire-and-forget background task helper.

``asyncio.create_task`` has two footguns for fire-and-forget work:

1. The event loop only keeps a *weak* reference to the task, so a task with no
   other reference can be garbage-collected mid-flight (documented CPython
   behaviour).
2. If the coroutine raises and nobody ever awaits the task, the exception is
   only surfaced as a noisy "Task exception was never retrieved" warning at GC
   time — and the failure is otherwise silent.

``spawn`` fixes both: it retains a strong reference until the task finishes and
attaches a done-callback that logs any exception through our structured logger.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.logging import get_logger

logger = get_logger("background")

# Strong references to in-flight tasks so the loop can't GC them mid-run.
_TASKS: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    """Schedule *coro* as a fire-and-forget task that logs its own failures.

    Args:
        coro: The coroutine to run.
        name: Short identifier used in the failure log line (e.g. "ws_push").

    Returns:
        The scheduled task (callers may ignore it — a reference is retained
        internally until completion).
    """
    task = asyncio.create_task(coro, name=name)
    _TASKS.add(task)

    def _done(t: asyncio.Task[Any]) -> None:
        _TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.warning("background_task_failed", task=name, error=str(exc))

    task.add_done_callback(_done)
    return task
