"""OpenTelemetry distributed tracing — auto-instrumentation + OTLP export.

Disabled by default. Enable with ``OTEL_ENABLED=true`` and point
``OTEL_EXPORTER_OTLP_ENDPOINT`` at a collector (Tempo/Jaeger/Honeycomb).

Auto-instrumentation covers the full request path:
  FastAPI (incoming spans + context extraction) → httpx (outgoing spans +
  W3C traceparent propagation) → SQLAlchemy + Redis (dependency spans).

Because httpx propagates ``traceparent`` automatically, the existing internal
calls (gateway → ai-agent → closet-service, carrying X-Internal-Token) are
stitched into one distributed trace as long as each service runs setup_tracing.
All packages are imported defensively so a missing dep never breaks startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("tracing")
settings = get_settings()

_initialized = False


def setup_tracing(app: "FastAPI") -> None:
    """Initialise OTel tracing and instrument the app. No-op when disabled."""
    global _initialized
    if not settings.otel_enabled:
        return
    if _initialized:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError as exc:
        logger.warning("tracing_unavailable", reason=f"opentelemetry packages missing: {exc}")
        return

    try:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(
            resource=resource,
            sampler=TraceIdRatioBased(settings.otel_traces_sample_rate),
        )
        endpoint = settings.otel_exporter_otlp_endpoint or None
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)

        # Instrument frameworks/clients. Health/metrics excluded from HTTP spans
        # to avoid trace noise from probes and scrapes.
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="/live,/health,/ready,/metrics"
        )
        HTTPXClientInstrumentor().instrument()
        _instrument_db_and_redis()

        _initialized = True
        logger.info(
            "tracing_enabled",
            service=settings.otel_service_name,
            endpoint=settings.otel_exporter_otlp_endpoint or "default",
            sample_rate=settings.otel_traces_sample_rate,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("tracing_init_failed", error=str(exc))


def _instrument_db_and_redis() -> None:
    """Best-effort SQLAlchemy + Redis instrumentation (non-fatal)."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.db.session import engine

        # Async engine exposes the underlying sync engine for instrumentation.
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception as exc:  # pragma: no cover
        logger.warning("tracing_sqlalchemy_skip", error=str(exc))

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        logger.warning("tracing_redis_skip", error=str(exc))
