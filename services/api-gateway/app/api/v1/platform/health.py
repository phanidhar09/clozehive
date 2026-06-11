"""Health check endpoints.

Three endpoints with distinct semantics:

  /live   — always 200 while the process is running (process-level liveness).
              Configure as the LIVENESS probe — restarts the pod if it hangs.

  /ready  — 200 only when the app can serve requests (DB + optional Redis).
              Configure as the READINESS probe — takes the pod out of the LB
              rotation when it returns 503 so traffic never hits a broken worker.

  /health — same DB + Redis probes as /ready, for human/dashboard use.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import cache_service
from app.core.config import get_settings
from app.db.session import engine

router = APIRouter()
settings = get_settings()

# Flipped to True at the start of graceful shutdown so /ready reports 503 and the
# load balancer drains this instance before connections are torn down.
_draining: bool = False


def begin_draining() -> None:
    """Mark the instance as draining — /ready will return 503 from now on."""
    global _draining
    _draining = True


def _startup_db_ok() -> bool:
    """Return the startup DB flag set by main.py lifespan."""
    try:
        import app.main as _main

        return _main._startup_db_ok
    except Exception:
        return False


def _startup_migrations_status() -> tuple[bool, str]:
    """Return startup migration success flag and optional error text."""
    try:
        import app.main as _main

        ok = bool(getattr(_main, "_startup_migrations_ok", True))
        err = str(getattr(_main, "_startup_migrations_error", "")) if not ok else ""
        return ok, err
    except Exception:
        return True, ""


async def check_database() -> tuple[bool, str]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        return False, f"error: {exc}"


async def check_redis() -> tuple[bool, str]:
    try:
        redis_ok = await cache_service.ping()
        if not redis_ok:
            return False, "error: ping failed"
        return True, "ok"
    except Exception as exc:
        return False, f"error: {exc}"


async def health_payload() -> tuple[int, dict]:
    """Backward-compatible aggregate status (DB + Redis when checked)."""
    db_ok, db_msg = await check_database()
    redis_ok, redis_msg = True, "skipped"
    if settings.redis_check_on_ready:
        redis_ok, redis_msg = await check_redis()

    status_code = 200 if db_ok and redis_ok else 503
    body = {
        "status": "healthy" if status_code == 200 else "unhealthy",
        "db": db_msg,
        "redis": redis_msg,
        "version": settings.app_version,
    }
    return status_code, body


async def ready_payload() -> tuple[int, dict]:
    # Draining: shutting down. Report not-ready so the LB stops routing here.
    if _draining:
        return 503, {
            "status": "draining",
            "db": "skipped",
            "redis": "skipped",
            "version": settings.app_version,
        }

    # Fast-path: if DB was unreachable at startup we already know we're not ready.
    # Skip the live probe so /ready is cheap under high readiness-check frequency.
    if not _startup_db_ok():
        return 503, {
            "status": "not_ready",
            "db": "error: database was unreachable at startup",
            "migrations": "skipped",
            "redis": "skipped",
            "version": settings.app_version,
        }

    mig_ok, mig_err = _startup_migrations_status()
    if not mig_ok:
        return 503, {
            "status": "not_ready",
            "db": "ok",
            "migrations": f"error: {mig_err or 'startup migrations failed'}",
            "redis": "skipped",
            "version": settings.app_version,
        }

    db_ok, db_msg = await check_database()
    redis_ok, redis_msg = True, "skipped"
    if settings.redis_check_on_ready:
        redis_ok, redis_msg = await check_redis()

    ok = db_ok and redis_ok
    body = {
        "status": "ready" if ok else "not_ready",
        "db": db_msg,
        "migrations": "ok",
        "redis": redis_msg,
        "version": settings.app_version,
    }
    return (200 if ok else 503), body


def live_payload() -> tuple[int, dict]:
    return 200, {"status": "alive", "version": settings.app_version}


@router.get("")
async def health() -> JSONResponse:
    status_code, body = await health_payload()
    return JSONResponse(status_code=status_code, content=body)
