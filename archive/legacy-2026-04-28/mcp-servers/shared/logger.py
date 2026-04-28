"""
Shared logger factory.
Usage:  logger = get_logger(__name__)
"""

import logging
import sys


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a named logger with a consistent format."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
