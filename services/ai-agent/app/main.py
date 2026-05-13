"""AI Agent Service — application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.agent.wardrobe_agent import get_agent
from app.api.v1.agent import router as agent_router
from app.core.config import get_settings
from app.services import vector_store

settings = get_settings()
logger = structlog.get_logger("ai_agent.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    import structlog as sl

    sl.configure(
        processors=[
            sl.contextvars.merge_contextvars,
            sl.stdlib.add_log_level,
            sl.processors.TimeStamper(fmt="iso"),
            sl.dev.ConsoleRenderer() if not settings.is_production else sl.processors.JSONRenderer(),
        ],
        wrapper_class=sl.stdlib.BoundLogger,
        logger_factory=sl.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger.info(
        "ai_agent_starting",
        enable_mcp_tools=settings.enable_mcp_tools,
        mcp_endpoints_summary=(
            settings.mcp_endpoints_for_logging() if settings.enable_mcp_tools else []
        ),
    )

    agent = get_agent()
    try:
        await agent.start()
        logger.info("ai_agent_ready", tools=agent.available_tools)
    except Exception as exc:
        logger.error("ai_agent_start_failed", error=str(exc))
        # Continue in degraded mode — /health will report not ready

    yield

    await agent.stop()
    await vector_store.close()
    logger.info("ai_agent_shutdown")


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """Reject requests that don't carry the shared internal service token.

    Only enforced when ``internal_service_token`` is non-empty. Health and
    docs endpoints are always allowed so Docker health-checks keep working.
    """

    _SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next) -> Response:
        token = settings.internal_service_token
        if not token or request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        if request.headers.get("X-Internal-Token") != token:
            return Response(
                content='{"detail":"Forbidden — missing or invalid internal service token"}',
                status_code=403,
                media_type="application/json",
            )
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Internal token check must run before CORS so unauthenticated external
    # callers get 403, not a CORS preflight success.
    app.add_middleware(InternalTokenMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(agent_router, prefix="/api/v1")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, Any]:
        agent = get_agent()
        ready = agent.is_ready and settings.has_valid_openai_key
        return {
            "status": "ok" if ready else "degraded",
            "service": settings.app_name,
            "version": settings.app_version,
            "agent_ready": agent.is_ready,
            "openai_configured": settings.has_valid_openai_key,
            "enable_mcp_tools": settings.enable_mcp_tools,
            "mcp_tools_loaded_count": len(agent.available_tools),
            "tools": agent.available_tools,
        }

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
