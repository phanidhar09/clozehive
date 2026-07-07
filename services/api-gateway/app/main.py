"""
CLOZEHIVE API Gateway — application factory and lifespan.
This is the entry-point for uvicorn.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import Response as StarletteResponse

from app.api.v1.platform.health import health_payload, live_payload, ready_payload
from app.api.v1.router import api_router
from app.api.v1.travel.services import weather_service
from app.core import cache_service
from app.core.config import get_settings
from app.core.error_response import json_error
from app.core.exceptions import AppError, app_error_handler, http_exception_handler, unhandled_error_handler
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter
from app.db.session import connect as db_connect
from app.db.session import disconnect as db_disconnect
from app.middleware.etag import ETagMiddleware
from app.middleware.logging import AccessLogMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

# Non-MVP: Firestore is optional — import conditionally
try:
    from app.services.firestore.firestore_client import (
        close_firestore as _close_firestore,
    )
    from app.services.firestore.firestore_client import (
        init_firestore as _init_firestore,
    )
except ImportError:

    def _close_firestore() -> None:  # type: ignore
        return None

    def _init_firestore() -> None:
        return None


settings = get_settings()
logger = get_logger("main")

# Tracks whether the DB was reachable at startup.  Used by /ready so the load
# balancer stops routing traffic when the DB is down instead of letting requests
# hit the worker and fail with 500s.
_startup_db_ok: bool = False
_startup_migrations_ok: bool = True
_startup_migrations_error: str = ""

# ── Lifespan ──────────────────────────────────────────────────────────────────


async def rate_limit_handler(request: Request, _exc: Exception) -> JSONResponse:
    return json_error(
        request,
        detail="Too many requests. Please wait before trying again.",
        code="RATE_LIMITED",
        status_code=429,
    )


def _validation_errors(errors: Sequence[Any]) -> list[dict[str, str]]:
    clean_errors = []
    for error in errors:
        loc = [str(part) for part in error.get("loc", []) if part not in {"body", "query", "path"}]
        clean_errors.append(
            {
                "field": ".".join(loc) or "request",
                "message": str(error.get("msg", "Invalid value")),
            }
        )
    return clean_errors


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError | ValidationError)
    return json_error(
        request,
        detail="Validation failed",
        code="VALIDATION_ERROR",
        status_code=422,
        extra={"errors": _validation_errors(exc.errors())},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_db_ok, _startup_migrations_ok, _startup_migrations_error
    setup_logging()
    logger.info("startup", service=settings.app_name, version=settings.app_version, env=settings.environment)

    # PostgreSQL — primary store for users, closet, trips, packing plans, outfits, etc.
    try:
        await db_connect()
        _startup_db_ok = True
    except Exception as exc:
        logger.error("startup_db_failed", error=str(exc))
        if settings.is_production:
            # In production, crash the process so the platform (Render, k8s) keeps
            # the previous healthy version running instead of routing traffic to a
            # worker that cannot reach its database.
            raise RuntimeError(f"DB unreachable at startup — refusing to start in production: {exc}") from exc
        # In development/staging, log and continue so the process stays up for
        # debugging.  The /ready endpoint will return 503 until DB is available.
        logger.warning("startup_db_failed_continuing", msg="DB unreachable — /ready will return 503")

    # Apply DB migrations on startup when enabled (hosts without shell/pre-deploy,
    # e.g. Render free tier). Run them in the BACKGROUND — never block the lifespan
    # on migrations. Blocking here caused production boot loops: a hung/slow
    # `alembic upgrade head` (e.g. an orphaned Postgres backend holding the
    # alembic_version lock) kept the port from binding → /live health check timed
    # out → Render killed and restarted the instance → repeat forever. Now the app
    # always becomes live; /ready reflects migration status (see _startup_migrations_*),
    # and the 15s lock_timeout in alembic/env.py makes a blocked migration fail fast.
    if settings.run_migrations_on_startup:
        logger.info("startup_migrations_begin")
        import asyncio as _asyncio_mig

        from app.core.db_migrate import run_migrations_on_startup as _apply_migrations

        async def _run_startup_migrations() -> None:
            global _startup_migrations_ok, _startup_migrations_error
            # raise_on_error is forced False: a background-task exception can't
            # (and must not) crash the already-serving process. Readiness, not
            # liveness, gates traffic on migration success.
            ok = await _apply_migrations(raise_on_error=False)
            _startup_migrations_ok = ok
            _startup_migrations_error = "" if ok else "startup migrations failed"
            if not ok:
                logger.error("startup_migrations_failed_readiness_blocked")

        app.state.migration_task = _asyncio_mig.create_task(_run_startup_migrations())

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

    # Account-deletion saga: background reconciliation loop retries any pending
    # cross-service purges (survives restarts — the outbox lives in Postgres).
    import asyncio as _asyncio

    from app.api.v1.identity.services.account_purge_service import reconcile_loop

    app.state.purge_reconcile_task = _asyncio.create_task(reconcile_loop())

    logger.info("api_gateway_ready", port=settings.port)

    # PostHog LLM analytics (token/cost/latency capture). No-op if unconfigured.
    from app.core.analytics import init_analytics

    init_analytics()

    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                release=settings.app_version,
                traces_sample_rate=settings.sentry_traces_sample_rate,
                # Tie Sentry performance traces to the same trace ids as OTel so
                # an error in Sentry links to its distributed trace.
                send_default_pii=False,
            )
            logger.info("sentry_initialized", environment=settings.environment)
        except Exception as exc:
            logger.warning("sentry_init_failed", error=str(exc))
    elif settings.is_production:
        # No Sentry in production means every unhandled exception is logged
        # to stdout only — no alerting, no grouping, no stack traces in a UI.
        # Set SENTRY_DSN to enable error observability.
        logger.warning(
            "sentry_not_configured",
            msg="SENTRY_DSN is unset — production errors will not be captured in Sentry. "
            "Set SENTRY_DSN to enable error observability.",
        )

    yield

    # Shutdown — drain first so the load balancer stops routing to this instance
    # before we tear down DB/Redis connections and cut in-flight requests.
    if settings.shutdown_drain_seconds > 0:
        from app.api.v1.platform.health import begin_draining

        begin_draining()
        logger.info("draining", seconds=settings.shutdown_drain_seconds)
        import asyncio

        await asyncio.sleep(settings.shutdown_drain_seconds)

    task = getattr(app.state, "purge_reconcile_task", None)
    if task is not None:
        task.cancel()

    from app.core.analytics import shutdown_analytics

    shutdown_analytics()

    await db_disconnect()
    await cache_service.close()
    await weather_service.close_client()
    await _close_firestore()
    logger.info("shutdown_complete")


# ── Static uploads with long-lived cache headers ──────────────────────────────
# Uploaded images are effectively immutable: a new upload always gets a fresh
# filename, so the bytes at a given /uploads/<name> never change. Serve them with
# a long max-age + immutable so browsers and any CDN in front cache aggressively.
# (In production GCS/CDN usually serves images directly; this covers local disk
# and any origin pulls the CDN makes.)
class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> StarletteResponse:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    cors_origins = list(dict.fromkeys(settings.origins_list))
    if not cors_origins:
        logger.warning(
            "cors_no_origins_configured", msg="ALLOWED_ORIGINS is empty — browser clients cannot call the API"
        )

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
    if settings.http_cache_validation:
        # Inner enough to see the final JSON body; emits ETag / 304.
        app.add_middleware(ETagMiddleware)
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

    # Observability: Prometheus /metrics (gated by ENABLE_METRICS) and
    # OpenTelemetry distributed tracing (gated by OTEL_ENABLED).
    from app.core.metrics import setup_metrics
    from app.core.tracing import setup_tracing

    setup_metrics(app)
    setup_tracing(app)

    app.mount("/uploads", CachedStaticFiles(directory=settings.upload_path), name="uploads")

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
