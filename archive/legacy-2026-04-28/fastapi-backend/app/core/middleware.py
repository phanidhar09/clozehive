"""
Application-level middleware: CORS, rate limiting, request logging.
"""
from __future__ import annotations

import time
import uuid
import logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger("clozehive.request")


# ── Rate Limiter (slowapi) ───────────────────────────────────────────────────
# Use Redis when available, fall back to in-memory storage gracefully.

def _make_limiter() -> Limiter:
    try:
        import redis as _sync_redis
        r = _sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        logger.info("Rate limiter: using Redis storage (%s)", settings.REDIS_URL)
        return Limiter(
            key_func=get_remote_address,
            default_limits=[settings.RATE_LIMIT_DEFAULT],
            storage_uri=settings.REDIS_URL,
        )
    except Exception:
        logger.warning("Rate limiter: Redis unavailable — using in-memory storage.")
        return Limiter(
            key_func=get_remote_address,
            default_limits=[settings.RATE_LIMIT_DEFAULT],
        )


limiter = _make_limiter()


def register_middleware(app: FastAPI) -> None:
    """
    Attach all middleware to the FastAPI application.
    Order matters — outermost first.
    """

    # 1. Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # 3. Request ID + timing
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1_000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

        logger.info(
            "%s %s → %d  [%.2fms] req_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
