"""ETag / conditional-GET middleware.

For cacheable JSON GET responses we hash the body into a strong ``ETag`` and,
when the client sends a matching ``If-None-Match``, return ``304 Not Modified``
with no body. This turns repeated polls of unchanged data (closet list, profile,
analytics) into a few-byte 304 instead of a full re-send.

Scoped to an allowlist of read-only prefixes and to ``application/json`` 200
responses, so streaming/SSE/WebSocket/upload paths are never buffered.
"""

from __future__ import annotations

import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

_settings = get_settings()

# Only buffer + ETag these read-only JSON collections. str.startswith accepts a
# tuple, so this is a cheap prefix check.
_CACHEABLE_PREFIXES = (
    "/api/v1/closet",
    "/api/v1/profile",
    "/api/v1/analytics",
    "/api/v1/outfits",
)


def _strong_etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


class ETagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.method != "GET" or response.status_code != 200:
            return response
        if not request.url.path.startswith(_CACHEABLE_PREFIXES):
            return response
        if "application/json" not in response.headers.get("content-type", ""):
            return response

        # Buffer the JSON body (safe: these endpoints return bounded collections).
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk

        etag = _strong_etag(body)
        headers = dict(response.headers)
        headers["etag"] = etag
        # HTTP-layer stale-while-revalidate: cache briefly, then allow stale while
        # the browser/CDN revalidates in the background. Private user data, so the
        # cache is per-client (private), not shared.
        headers["cache-control"] = (
            f"private, max-age={_settings.http_cache_max_age}, stale-while-revalidate={_settings.http_cache_swr}"
        )

        # Client already has this exact representation → 304, no body.
        if request.headers.get("if-none-match") == etag:
            headers.pop("content-length", None)
            return Response(status_code=304, headers=headers)

        headers.pop("content-length", None)  # Response recomputes it
        return Response(content=body, status_code=200, headers=headers)
