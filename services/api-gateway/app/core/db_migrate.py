"""Run Alembic migrations programmatically at application startup.

WHY THIS EXISTS
───────────────
Some hosting tiers (e.g. Render free tier) provide neither a shell nor a
pre-deploy command hook, so there is no way to run ``alembic upgrade head``
out-of-band before the app boots.  This module lets the app apply migrations
itself on startup, gated behind the ``RUN_MIGRATIONS_ON_STARTUP`` setting.

SAFETY
──────
- ``alembic/env.py`` runs its async migrations via ``asyncio.run(...)``. Calling
  it from within the live FastAPI event loop would raise "asyncio.run() cannot
  be called from a running event loop", so we execute the (blocking) Alembic
  command in a worker thread via ``asyncio.to_thread`` — that thread has no
  running loop, so ``asyncio.run`` works correctly.
- Idempotent: running ``upgrade head`` when already at head is a no-op.
- Failures are logged but never re-raised: a migration error must not crash the
  process into a boot-loop. The app still starts; DB-dependent requests will
  surface the error, and the failure is clearly logged in the deploy output.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger("db_migrate")

# app/core/db_migrate.py → core → app → <api-gateway root> (where alembic.ini lives)
_API_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _API_ROOT / "alembic.ini"
_ALEMBIC_DIR = _API_ROOT / "alembic"


def _run_upgrade_sync() -> None:
    """Blocking Alembic upgrade — must run in a worker thread (see module docstring)."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    # Resolve script_location absolutely so it works regardless of the process CWD.
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    command.upgrade(cfg, "head")


async def run_migrations_on_startup(*, raise_on_error: bool = False) -> bool:
    """Apply all pending migrations up to head. Returns True on success."""
    if not _ALEMBIC_INI.exists():
        logger.warning("alembic_ini_not_found", path=str(_ALEMBIC_INI))
        return False
    try:
        await asyncio.to_thread(_run_upgrade_sync)
        logger.info("migrations_applied", target="head")
        return True
    except Exception as exc:
        logger.error("migrations_failed", error=str(exc), error_type=type(exc).__name__)
        if raise_on_error:
            raise RuntimeError(f"Startup migrations failed: {exc}") from exc
        return False
