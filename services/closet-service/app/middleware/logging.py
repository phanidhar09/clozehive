"""
Access log middleware — logs method, path, status, and latency for every request.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger("http")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", request.headers.get("X-Request-ID", "unknown"))
        logger.info(
            "request_start",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "request_error",
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed_ms,
                request_id=request_id,
            )
            raise

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_end",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=elapsed_ms,
            request_id=request_id,
        )
        return response
