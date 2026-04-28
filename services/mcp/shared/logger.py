"""Structured logging helper for MCP servers."""

from __future__ import annotations

import logging
import os
import sys

import structlog


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger configured for the current environment."""
    env = os.getenv("ENVIRONMENT", "development")

    if not structlog.is_configured():
        # Route structlog through the stdlib logging system so processors like
        # `add_logger_name` (which reads `logger.name`) work. Using PrintLogger
        # here caused `AttributeError: 'PrintLogger' object has no attribute 'name'`.
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.INFO,
        )

        shared_processors: list = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
        ]

        if env == "production":
            processors = shared_processors + [structlog.processors.JSONRenderer()]
        else:
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=False),
            ]

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)

    return structlog.get_logger(name)
