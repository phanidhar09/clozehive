"""Deprecated entrypoint.

The worker now runs on ARQ (Redis), not Kafka. Start it with::

    arq app.worker.WorkerSettings

This module is kept only so stale ``python -m app.main`` invocations fail loudly
with a clear message instead of an obscure import error.
"""

from __future__ import annotations

import sys


def main() -> None:
    sys.exit(
        "ai-worker now runs on ARQ. Start it with:\n"
        "    arq app.worker.WorkerSettings\n"
        "(the container CMD already does this)."
    )


if __name__ == "__main__":
    main()
