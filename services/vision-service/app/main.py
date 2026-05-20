"""
Vision Service — application factory and lifespan.
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

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.error_response import json_error
from app.core.exceptions import AppError, app_error_handler, http_exception_handler, unhandled_error_handler
from app.core.logging import get_logger, setup_logging
from app.db.session import connect as db_connect, disconnect as db_disconnect
from app.services import cache_service

settings = get_settings()
logger = get_logger("main")


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
    logger.info("startup", service="vision-service", env=settings.environment)

    # PostgreSQL
    try:
        await db_connect()
    except Exception as exc:
        logger.error("startup_db_failed", error=str(exc),
                     msg="DB unreachable at startup — app will start but DB requests will fail")

    # Redis (best-effort)
    redis_ok = await cache_service.ping()
    if not redis_ok:
        logger.warning("redis_unavailable", msg="Cache disabled — running without Redis")

    logger.info("vision_service_ready", port=8002)

    yield

    # Shutdown
    await db_disconnect()
    await cache_service.close()
    logger.info("shutdown_complete")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Vision Service",
        version="1.0.0",
        description="CLOZEHIVE Vision Service — clothing detection and background removal",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # Health endpoints at root
    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        return JSONResponse(status_code=200, content={"status": "ok", "service": "vision-service"})

    @app.get("/live", include_in_schema=False)
    async def live() -> JSONResponse:
        return JSONResponse(status_code=200, content={"status": "live", "service": "vision-service"})

    # Mount uploads for local dev
    try:
        app.mount("/uploads", StaticFiles(directory=settings.upload_path), name="uploads")
    except Exception:
        pass

    return app


app = create_app()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,
        reload=settings.debug,
        log_config=None,
    )
