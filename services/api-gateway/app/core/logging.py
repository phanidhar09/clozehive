"""
Structured JSON logging with structlog.
Import: from app.core.logging import get_logger, setup_logging
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings


def _add_service(_logger, _method_name, event_dict):
    event_dict["service"] = "api-gateway"
    return event_dict


def _rename_event(_logger, _method_name, event_dict):
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _uppercase_level(_logger, _method_name, event_dict):
    if "level" in event_dict:
        event_dict["level"] = str(event_dict["level"]).upper()
    return event_dict


def _add_trace_context(_logger, _method_name, event_dict):
    """Inject the active OpenTelemetry trace_id/span_id so logs join to traces.

    No-op when OTel isn't installed or there is no active span (e.g. tracing
    disabled). The hex ids match what Tempo/Jaeger/Grafana use, so a log line
    links directly to its distributed trace.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx is not None and ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:
        pass
    return event_dict


def setup_logging() -> None:
    """Call once at app startup (in main.py lifespan)."""
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _uppercase_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        _add_service,
        _add_trace_context,
        _rename_event,
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quieten noisy libraries
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
