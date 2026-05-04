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
    db_ok, db_msg = await check_database()
    redis_ok, redis_msg = True, "skipped"
    if settings.redis_check_on_ready:
        redis_ok, redis_msg = await check_redis()

    ok = db_ok and redis_ok
    body = {
        "status": "ready" if ok else "not_ready",
        "db": db_msg,
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
