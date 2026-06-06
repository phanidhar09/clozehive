"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.services import cache_service

router = APIRouter()
settings = get_settings()


def _startup_db_ok() -> bool:
    """Return the startup DB flag set by main.py lifespan."""
    try:
        import app.main as _main
        return bool(getattr(_main, "_startup_db_ok", False))
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
