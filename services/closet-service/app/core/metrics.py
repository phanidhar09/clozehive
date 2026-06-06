"""Prometheus metrics wiring for closet-service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("metrics")
settings = get_settings()


def setup_metrics(app: "FastAPI") -> None:
    """Instrument the app and expose /metrics. No-op when disabled/unavailable."""
    if not settings.enable_metrics:
        logger.info("metrics_disabled", reason="ENABLE_METRICS is false")
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.warning("metrics_unavailable", reason="prometheus-fastapi-instrumentator not installed")
        return

    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/live", "/health", "/ready"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    logger.info("metrics_enabled", endpoint="/metrics")
