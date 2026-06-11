"""Prometheus metrics — HTTP RED signals + custom business metrics.

All metrics are no-ops unless ``ENABLE_METRICS`` is true and the optional
prometheus packages are installed, so importing this module is always safe.

Exposed at ``GET /metrics`` (see ``setup_metrics``). Scrape it with Prometheus
(see ``infra/observability/prometheus.yml``).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("metrics")
settings = get_settings()

# Optional deps — import defensively so the app runs even if absent.
try:
    from prometheus_client import Counter, Gauge, Histogram

    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False


# ── Metric definitions ────────────────────────────────────────────────────────
# Defined only when prometheus_client is present. Helper wrappers below are
# always callable and become no-ops when metrics are unavailable.

if _PROM_AVAILABLE:
    AI_REQUEST_DURATION = Histogram(
        "clozehive_ai_request_duration_seconds",
        "Latency of AI/LLM calls.",
        labelnames=("operation", "model", "outcome"),
        buckets=(0.25, 0.5, 1, 2, 4, 8, 15, 30, 60),
    )
    AI_TOKENS = Counter(
        "clozehive_ai_tokens_total",
        "LLM tokens consumed.",
        labelnames=("model", "kind"),  # kind: prompt | completion
    )
    CACHE_OPS = Counter(
        "clozehive_cache_operations_total",
        "Cache get operations by result.",
        labelnames=("result",),  # hit | miss | error
    )
    EMBEDDING_JOBS = Counter(
        "clozehive_embedding_jobs_total",
        "Closet embedding refresh jobs scheduled, by transport.",
        labelnames=("transport",),  # arq | inprocess
    )
    VISION_STAGE_DURATION = Histogram(
        "clozehive_vision_stage_duration_seconds",
        "Vision pipeline stage durations.",
        labelnames=("stage",),  # compress | detect | bg_removal | total
        buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30),
    )
    DB_POOL_IN_USE = Gauge(
        "clozehive_db_pool_connections_in_use",
        "Checked-out DB connections per engine.",
        labelnames=("engine",),  # primary | replica
    )
    CIRCUIT_STATE = Gauge(
        "clozehive_circuit_breaker_state",
        "Circuit breaker state per dependency (0 closed, 1 half-open, 2 open).",
        labelnames=("breaker",),
    )
    PURGE_FAILED = Counter(
        "clozehive_account_purge_failed_total",
        "Account-deletion downstream purges that exhausted retries (need manual fix).",
    )
    WEB_VITALS = Histogram(
        "clozehive_web_vital",
        "Frontend Core Web Vitals reported by browsers (RUM).",
        labelnames=("metric", "rating"),  # metric: LCP|INP|CLS|FCP|TTFB
        # Mixed units (ms + unitless CLS); generous buckets cover both.
        buckets=(0.1, 0.25, 0.5, 1, 1.5, 2.5, 4, 100, 200, 500, 1000, 2500, 4000, 8000),
    )


# ── Always-safe wrappers ──────────────────────────────────────────────────────


def record_ai_request(operation: str, model: str, outcome: str, seconds: float) -> None:
    if _PROM_AVAILABLE:
        AI_REQUEST_DURATION.labels(operation=operation, model=model, outcome=outcome).observe(seconds)


@contextmanager
def track_ai(operation: str, model: str = "agent"):
    """Time an AI call and record duration + outcome (ok | error)."""
    start = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except Exception:
        outcome = "error"
        raise
    finally:
        record_ai_request(operation, model, outcome, time.perf_counter() - start)


def record_ai_tokens(model: str, prompt: int = 0, completion: int = 0) -> None:
    if _PROM_AVAILABLE:
        if prompt:
            AI_TOKENS.labels(model=model, kind="prompt").inc(prompt)
        if completion:
            AI_TOKENS.labels(model=model, kind="completion").inc(completion)


def record_cache(result: str) -> None:
    if _PROM_AVAILABLE:
        CACHE_OPS.labels(result=result).inc()


def record_embedding_job(transport: str) -> None:
    if _PROM_AVAILABLE:
        EMBEDDING_JOBS.labels(transport=transport).inc()


_CIRCUIT_STATES = {"closed": 0, "half_open": 1, "open": 2}


def record_circuit_state(breaker: str, state: str) -> None:
    if _PROM_AVAILABLE:
        CIRCUIT_STATE.labels(breaker=breaker).set(_CIRCUIT_STATES.get(state, 0))


def record_purge_failed() -> None:
    if _PROM_AVAILABLE:
        PURGE_FAILED.inc()


def record_vision_stage(stage: str, seconds: float) -> None:
    if _PROM_AVAILABLE:
        VISION_STAGE_DURATION.labels(stage=stage).observe(seconds)


_VITAL_NAMES = {"LCP", "INP", "CLS", "FCP", "TTFB"}
_VITAL_RATINGS = {"good", "needs-improvement", "poor"}


def record_web_vital(metric: str, value: float, rating: str) -> bool:
    """Record a browser-reported Web Vital. Returns False for invalid input
    (bounded label values prevent cardinality abuse from a public endpoint)."""
    metric = (metric or "").upper()
    rating = (rating or "").lower()
    if metric not in _VITAL_NAMES or rating not in _VITAL_RATINGS:
        return False
    if _PROM_AVAILABLE:
        WEB_VITALS.labels(metric=metric, rating=rating).observe(value)
    return True


# ── App wiring ────────────────────────────────────────────────────────────────


def setup_metrics(app: FastAPI) -> None:
    """Instrument the app and expose /metrics. No-op when disabled/unavailable."""
    if not settings.enable_metrics:
        logger.info("metrics_disabled", reason="ENABLE_METRICS is false")
        return
    if not _PROM_AVAILABLE:
        logger.warning("metrics_unavailable", reason="prometheus_client not installed")
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.warning("metrics_unavailable", reason="prometheus-fastapi-instrumentator not installed")
        return

    # HTTP RED signals (request rate, errors, duration) per handler.
    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/live", "/health", "/ready"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    # DB pool saturation — read live from the engine pools via gauge callbacks.
    _wire_db_pool_gauges()
    logger.info("metrics_enabled", endpoint="/metrics")


def _wire_db_pool_gauges() -> None:
    """Bind the DB pool gauges to live pool state (best-effort)."""
    try:
        from app.db.session import engine, read_engine

        def _in_use(eng) -> float:
            try:
                return float(eng.pool.checkedout())  # type: ignore[attr-defined]
            except Exception:
                return 0.0

        DB_POOL_IN_USE.labels(engine="primary").set_function(lambda: _in_use(engine))
        if read_engine is not engine:
            DB_POOL_IN_USE.labels(engine="replica").set_function(lambda: _in_use(read_engine))
    except Exception as exc:  # pragma: no cover
        logger.warning("db_pool_gauge_wire_failed", error=str(exc))
