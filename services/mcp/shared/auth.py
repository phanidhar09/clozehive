"""Bearer token guard for MCP SSE servers.

Usage in each server's main block:

    import uvicorn
    from shared.auth import BearerTokenMiddleware
    from shared.config import get_settings

    settings = get_settings()
    app = mcp.sse_app()
    if settings.internal_service_token:
        app = BearerTokenMiddleware(app, settings.internal_service_token)
    uvicorn.run(app, host=settings.host, port=settings.port)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_SKIP_PATHS = {"/health", "/docs", "/openapi.json"}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[len("Bearer "):] != self._token:
            return JSONResponse({"detail": "Forbidden — invalid or missing service token"}, status_code=403)
        return await call_next(request)


def make_bearer_middleware(token: str):
    """Return a Starlette middleware factory accepted by FastMCP / Starlette."""
    def _middleware(app):
        return BearerTokenMiddleware(app, token)
    return _middleware
