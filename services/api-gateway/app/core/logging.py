"""
Structured logging with structlog.
JSON in production, pretty console in development.
Import: from app.core.logging import get_logger, setup_logging
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings


def setup_logging() -> None:
    """Call once at app startup (in main.py lifespan)."""
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON renderer for log aggregation (DataDog, ELK, CloudWatch)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable for local dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)

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
