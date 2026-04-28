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
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=elapsed_ms,
            client=request.client.host if request.client else "unknown",
        )
        return response
