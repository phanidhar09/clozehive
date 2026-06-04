"""
CLOZEHIVE API Gateway — application factory and lifespan.
This is the entry-point for uvicorn.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.api.v1.health import health_payload, live_payload, ready_payload
from app.core.config import get_settings
from app.core.error_response import json_error
from app.core.exceptions import AppError, app_error_handler, http_exception_handler, unhandled_error_handler
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter
from app.db.session import connect as db_connect, disconnect as db_disconnect
from app.middleware.logging import AccessLogMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services import ai_client, cache_service

# Non-MVP: Firestore is optional — import conditionally
try:
    from app.services.firestore.firestore_client import (
        close_firestore as _close_firestore,
        init_firestore as _init_firestore,
    )
except ImportError:
    _close_firestore = lambda: None  # type: ignore
    _init_firestore = lambda: None  # type: ignore

settings = get_settings()
logger = get_logger("main")

# ── Lifespan ──────────────────────────────────────────────────────────────────

async def rate_limit_handler(request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return json_error(
        request,
        detail="Too many requests. Please wait before trying again.",
        code="RATE_LIMITED",
        status_code=429,
    )


def _validation_errors(errors: list[dict]) -> list[dict[str, str]]:
    clean_errors = []
    for error in errors:
        loc = [str(part) for part in error.get("loc", []) if part not in {"body", "query", "path"}]
        clean_errors.append({
            "field": ".".join(loc) or "request",
            "message": str(error.get("msg", "Invalid value")),
        })
    return clean_errors


async def validation_exception_handler(request: Request, exc: RequestValidationError | ValidationError) -> JSONResponse:
    return json_error(
        request,
        detail="Validation failed",
        code="VALIDATION_ERROR",
        status_code=422,
        extra={"errors": _validation_errors(exc.errors())},
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("startup", service=settings.app_name, version=settings.app_version, env=settings.environment)

    # PostgreSQL — primary store for users, closet, trips, packing plans, outfits, etc.
    try:
        await db_connect()
    except Exception as exc:
        logger.error("startup_db_failed", error=str(exc),
                     msg="DB unreachable at startup — app will start but requests requiring DB will fail")
        # Do not re-raise: allow Render health check to pass so we can debug via shell

    # Apply DB migrations on startup when enabled (hosts without shell/pre-deploy,
    # e.g. Render free tier). Idempotent and non-fatal — see app/core/db_migrate.
    if settings.run_migrations_on_startup:
        logger.info("startup_migrations_begin")
        from app.core.db_migrate import run_migrations_on_startup as _apply_migrations
        await _apply_migrations()

    # Optional Firestore (legacy / non-MVP paths only; Phase 1 closet + trips live in Postgres)
    try:
        _init_firestore()
    except Exception as exc:
        logger.warning(
            "firestore_unavailable",
            error=str(exc),
            msg="Running without Firestore — optional Firestore-backed features disabled",
        )

    # Redis (best-effort)
    redis_ok = await cache_service.ping()
    if not redis_ok:
        logger.warning("redis_unavailable", msg="Cache disabled — running without Redis")

    logger.info("api_gateway_ready", port=settings.port)

    if settings.sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=0.1 if settings.is_production else 1.0,
            )
            logger.info("sentry_initialized", environment=settings.environment)
        except Exception as exc:
            logger.warning("sentry_init_failed", error=str(exc))

    yield

    # Shutdown
    await db_disconnect()
    await cache_service.close()
    await ai_client.close_client()
    await _close_firestore()
    from app.core.task_queue import close_arq_pool
    await close_arq_pool()
    logger.info("shutdown_complete")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    cors_origins = list(dict.fromkeys(settings.origins_list))
    if not cors_origins:
        logger.warning("cors_no_origins_configured", msg="ALLOWED_ORIGINS is empty — browser clients cannot call the API")

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
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Rate limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Routes ────────────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str | dict[str, str]]:
        """Browser-friendly index: there is no HTML landing page; API is under /api/v1."""
        endpoints: dict[str, str] = {
            "api_v1": "/api/v1",
            "live": "/live",
            "health": "/health",
            "ready": "/ready",
            "uploads": "/uploads",
        }
        if not settings.is_production:
            endpoints["openapi_docs"] = "/docs"
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "message": "JSON API — use endpoints below (no HTML at /).",
            "endpoints": endpoints,
        }

    app.include_router(api_router)

    # Internal service-to-service routes (token-protected, outside /api/v1).
    from app.api.internal import router as internal_router
    app.include_router(internal_router)

    app.mount("/uploads", StaticFiles(directory=settings.upload_path), name="uploads")

    @app.get("/health", tags=["health"], include_in_schema=False)
    async def health() -> JSONResponse:
        status_code, body = await health_payload()
        return JSONResponse(status_code=status_code, content=body)

    @app.get("/live", tags=["health"], include_in_schema=False)
    async def live() -> JSONResponse:
        status_code, body = live_payload()
        return JSONResponse(status_code=status_code, content=body)

    @app.get("/ready", tags=["health"], include_in_schema=False)
    async def ready() -> JSONResponse:
        status_code, body = await ready_payload()
        return JSONResponse(status_code=status_code, content=body)

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
