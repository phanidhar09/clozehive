"""Prometheus metrics for ai-worker queue depth and job SLA."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("worker_metrics")

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False


if _PROM_AVAILABLE:
    JOBS_TOTAL = Counter(
        "clozehive_ai_worker_jobs_total",
        "AI worker jobs by task and outcome.",
        labelnames=("task", "outcome"),  # outcome: completed | failed
    )
    JOB_DURATION = Histogram(
        "clozehive_ai_worker_job_duration_seconds",
        "End-to-end AI worker job latency from accepted to terminal state.",
        labelnames=("task",),
        buckets=(1, 2, 5, 10, 20, 30, 60, 120, 180, 300, 600),
    )
    SLA_BREACHES = Counter(
        "clozehive_ai_worker_sla_breaches_total",
        "Worker jobs exceeding configured SLA threshold.",
        labelnames=("task",),
    )
    QUEUE_DEPTH = Gauge(
        "clozehive_arq_queue_depth",
        "Current ARQ queue depth (jobs waiting to start).",
        labelnames=("queue",),
    )


def start_metrics_server() -> None:
    if not settings.enable_metrics:
        logger.info("worker_metrics_disabled", reason="ENABLE_METRICS is false")
        return
    if not _PROM_AVAILABLE:
        logger.warning("worker_metrics_unavailable", reason="prometheus_client not installed")
        return
    start_http_server(settings.metrics_port)
    logger.info("worker_metrics_enabled", port=settings.metrics_port)


def record_job_terminal(task: str, outcome: str, duration_seconds: float) -> None:
    if not (_PROM_AVAILABLE and settings.enable_metrics):
        return
    JOBS_TOTAL.labels(task=task, outcome=outcome).inc()
    JOB_DURATION.labels(task=task).observe(max(duration_seconds, 0.0))
    if duration_seconds > settings.ai_job_sla_seconds:
        SLA_BREACHES.labels(task=task).inc()


def set_queue_depth(depth: int) -> None:
    if not (_PROM_AVAILABLE and settings.enable_metrics):
        return
    QUEUE_DEPTH.labels(queue=settings.arq_queue_name).set(max(depth, 0))
