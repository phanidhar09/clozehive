"""
CLOZEHIVE — FastAPI application entry point.

Startup order:
  1. Register middleware (CORS, rate limiting, request logging)
  2. Connect to Redis
  3. Create / verify database tables
  4. Start Redis pub/sub listener for WebSocket broadcasting
  5. Register all API routers
  6. Register WebSocket endpoint
"""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, WebSocket
from fastapi.responses import ORJSONResponse

from app.core.config import settings
from app.core.middleware import register_middleware
from app.api.v1.router import api_router
from app.db.init_db import create_all_tables
from app.services.cache_service import cache, close_redis, get_redis
from app.websockets.handlers import websocket_endpoint
from app.websockets.manager import ws_manager

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("clozehive")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        default_response_class=ORJSONResponse,
        description=(
            "**CLOZEHIVE** — AI-powered wardrobe & travel stylist.\n\n"
            "All protected endpoints require `Authorization: Bearer <access_token>`."
        ),
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    register_middleware(app)

    # ── Startup / shutdown ────────────────────────────────────────────────────
    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("⚡ Starting CLOZEHIVE API (%s)…", settings.APP_ENV)

        # Verify Redis connectivity
        redis = get_redis()
        try:
            await redis.ping()
            logger.info("✅ Redis connected: %s", settings.REDIS_URL)
        except Exception as exc:
            logger.warning("⚠️  Redis not available: %s — caching disabled.", exc)

        # Create DB tables (idempotent)
        if not settings.is_production:
            await create_all_tables()
            logger.info("✅ Database tables ready.")

        # Start WebSocket → Redis bridge (only if Redis is available)
        try:
            redis = get_redis()
            await redis.ping()
            await ws_manager.start_redis_subscriber()
            logger.info("✅ WebSocket manager started.")
        except Exception:
            logger.warning("⚠️  WebSocket Redis bridge skipped (Redis unavailable).")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await ws_manager.stop()
        await close_redis()
        from app.services.ai_service import close_http_client
        await close_http_client()
        logger.info("CLOZEHIVE API shut down cleanly.")

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── WebSocket ─────────────────────────────────────────────────────────────
    @app.websocket("/ws/{user_id}")
    async def ws_handler(websocket: WebSocket, user_id: int) -> None:
        await websocket_endpoint(websocket, user_id)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health() -> dict:
        redis = get_redis()
        redis_ok = False
        try:
            redis_ok = await redis.ping()
        except Exception:
            pass
        return {
            "status": "ok",
            "version": settings.APP_VERSION,
            "redis": "ok" if redis_ok else "unavailable",
        }

    return app


app = create_app()


# ── Dev entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
