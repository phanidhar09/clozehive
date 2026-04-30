"""
CLOZEHIVE API Gateway — application factory and lifespan.
This is the entry-point for uvicorn.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_error_handler
from app.core.logging import get_logger, setup_logging
from app.db.session import connect as db_connect, disconnect as db_disconnect
from app.events import producer as event_producer, result_listener
from app.middleware.logging import AccessLogMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.services import ai_client, cache_service
from app.services.firestore.firestore_client import (
    close_firestore as _close_firestore,
    init_firestore as _init_firestore,
)

settings = get_settings()
logger = get_logger("main")

# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.redis_url,
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("startup", service=settings.app_name, version=settings.app_version, env=settings.environment)

    # Database (Postgres — auth/users only)
    await db_connect()

    # Firestore (closet, social, feeds)
    try:
        _init_firestore()
    except Exception as exc:
        logger.warning("firestore_unavailable", error=str(exc), msg="Running without Firestore — closet/social routes will fail")

    # Redis (best-effort)
    redis_ok = await cache_service.ping()
    if not redis_ok:
        logger.warning("redis_unavailable", msg="Cache disabled — running without Redis")

    # Kafka producer + result listener (best-effort so local tests can run without Kafka)
    try:
        await event_producer.start()
        await result_listener.start()
    except Exception as exc:
        logger.warning("kafka_unavailable", error=str(exc))

    logger.info("api_gateway_ready", port=settings.port)
    yield

    # Shutdown
    await result_listener.stop()
    await event_producer.stop()
    await db_disconnect()
    await cache_service.close()
    await ai_client.close_client()
    await _close_firestore()
    logger.info("shutdown_complete")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="CLOZEHIVE — AI-powered wardrobe and travel stylist",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost first) ───────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Rate limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_router)
    app.mount("/uploads", StaticFiles(directory=settings.upload_path), name="uploads")

    @app.get("/health", tags=["Meta"], include_in_schema=False)
    async def health() -> dict[str, Any]:
        redis_ok = await cache_service.ping()
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "redis": "connected" if redis_ok else "unavailable",
        }

    return app


app = create_app()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,  # structlog handles logging
    )
