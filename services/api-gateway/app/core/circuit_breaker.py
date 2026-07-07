"""Lightweight async circuit breaker.

Protects calls to a flaky downstream (the ai-agent) so that when it is down we
fail fast instead of letting every request burn its full connect-timeout +
retry budget — which under load ties up workers and cascades.

States:
  closed    — calls flow normally; consecutive failures are counted.
  open      — after ``fail_max`` consecutive failures the breaker trips; calls
              fail immediately with ``CircuitOpenError`` for ``reset_timeout``.
  half-open — after the cooldown, one trial call is allowed through. Success
              closes the breaker; failure re-opens it.

No external dependency; state is per-process (each gateway worker has its own
breaker, which is fine — a down dependency trips them all quickly).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.logging import get_logger

logger = get_logger("circuit_breaker")

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the breaker is open."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"circuit '{name}' is open; retry in ~{retry_after:.1f}s")


class CircuitBreaker:
    def __init__(self, name: str, *, fail_max: int = 5, reset_timeout: float = 30.0) -> None:
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None  # None = not open

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if (time.monotonic() - self._opened_at) >= self.reset_timeout:
            return "half_open"
        return "open"

    def _record_success(self) -> None:
        if self._failures or self._opened_at is not None:
            logger.info("circuit_closed", name=self.name)
        self._failures = 0
        self._opened_at = None

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max and self._opened_at is None:
            self._opened_at = time.monotonic()
            logger.warning("circuit_opened", name=self.name, failures=self._failures)

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Run ``func`` through the breaker. Raises CircuitOpenError when open."""
        state = self.state
        if state == "open":
            retry_after = self.reset_timeout - (time.monotonic() - (self._opened_at or 0))
            _record_metric(self.name, "open")
            raise CircuitOpenError(self.name, max(0.0, retry_after))

        # closed or half_open: allow the call; half_open lets exactly one trial
        # through (concurrent trials are acceptable — first result decides).
        try:
            result = await func()
        except Exception:
            self._record_failure()
            _record_metric(self.name, self.state)
            raise
        else:
            self._record_success()
            _record_metric(self.name, "closed")
            return result


def _record_metric(name: str, state: str) -> None:
    """Best-effort breaker-state gauge for Grafana (0 closed / 1 half / 2 open)."""
    try:
        from app.core.metrics import record_circuit_state

        record_circuit_state(name, state)
    except Exception as exc:
        logger.debug("circuit_metric_emit_failed", error=str(exc), breaker=name)
