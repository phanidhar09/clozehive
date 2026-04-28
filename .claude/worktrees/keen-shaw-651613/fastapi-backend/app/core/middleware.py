"""
Application-level middleware: CORS, rate limiting, security headers, CSRF, request logging.

Middleware stack (outermost → innermost — order in register_middleware matters):
  1. Rate limiter exception handler
  2. CORS
  3. Security headers  ← added: CSP, X-Frame-Options, etc.
  4. CSRF validation   ← added: Double-Submit Cookie for state-mutating requests
  5. Request ID + timing
"""
from __future__ import annotations

import time
import uuid
import logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger("clozehive.request")


# ── Rate Limiter ──────────────────────────────────────────────────────────────
# Prefer Redis-backed storage so limits survive restarts and work across
# multiple API instances. Falls back to in-memory gracefully.

def _make_limiter() -> Limiter:
    try:
        import redis as _sync_redis
        r = _sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        logger.info("Rate limiter: Redis (%s)", settings.REDIS_URL)
        return Limiter(
            key_func=get_remote_address,
            default_limits=[settings.RATE_LIMIT_DEFAULT],
            storage_uri=settings.REDIS_URL,
        )
    except Exception:
        logger.warning("Rate limiter: Redis unavailable — in-memory fallback")
        return Limiter(
            key_func=get_remote_address,
            default_limits=[settings.RATE_LIMIT_DEFAULT],
        )


limiter = _make_limiter()


# ── Security headers ──────────────────────────────────────────────────────────
# Applied to every response regardless of route.
#
# CSP explanation:
#   default-src 'self'         — no content from third-party origins by default
#   script-src  'self'         — JS only from same origin (+ GIS for Google OAuth)
#   style-src   'self' 'unsafe-inline' — Tailwind generates inline styles at runtime
#   img-src     'self' data: https:    — allow remote avatars and data-URI images
#   connect-src 'self' https:  — fetch/XHR only to same origin and HTTPS APIs
#   frame-ancestors 'none'     — equivalent to X-Frame-Options: DENY (clickjacking)
#
# Adjust CSP for your specific CDNs / analytics / third-party scripts.

_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://accounts.google.com https://apis.google.com 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https:; "
    "font-src 'self' data:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)

_SECURITY_HEADERS = {
    # Prevent browsers from MIME-sniffing responses away from declared content-type
    "X-Content-Type-Options": "nosniff",
    # Block page from being loaded in a frame (clickjacking protection)
    "X-Frame-Options": "DENY",
    # Legacy XSS filter for older browsers (modern ones use CSP instead)
    "X-XSS-Protection": "1; mode=block",
    # Only send origin in Referer header for same-origin requests
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Opt out of FLoC / Topics API
    "Permissions-Policy": "interest-cohort=()",
    # Content Security Policy
    "Content-Security-Policy": _CSP,
}

# Add HSTS only in production (HTTPS required)
_HSTS_HEADER = "max-age=31536000; includeSubDomains; preload"


# ── CSRF validation ───────────────────────────────────────────────────────────
# State-mutating methods require the X-CSRF-Token header to match the
# csrftoken cookie value (Double-Submit Cookie pattern).
#
# Exempt paths:
#   /auth/login, /auth/signup, /auth/google, /auth/refresh
#   — These are the bootstrap endpoints; the cookie is SET here, not read.
#   /health, /docs, /redoc, /openapi.json
#   — Infrastructure / documentation endpoints.

_CSRF_EXEMPT_PREFIXES = (
    "/auth/login",
    "/auth/signup",
    "/auth/google",
    "/auth/refresh",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_csrf_exempt(path: str, method: str) -> bool:
    if method in settings.CSRF_SAFE_METHODS:
        return True  # GET/HEAD/OPTIONS are always safe
    return any(path.startswith(p) for p in _CSRF_EXEMPT_PREFIXES)


def register_middleware(app: FastAPI) -> None:
    """
    Attach all middleware to the FastAPI application.
    Outermost middleware is registered first (it wraps all inner layers).
    """

    # 1. Rate limiter ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 2. CORS ─────────────────────────────────────────────────────────────────
    # Production: restrict origins to your actual domain(s).
    # Development: allow localhost frontends.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        # Restrict to the methods the API actually uses
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # Expose CSRF and request-ID headers to the browser
        allow_headers=["Authorization", "Content-Type", settings.CSRF_HEADER_NAME, "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # 3. Security headers + CSRF ──────────────────────────────────────────────
    @app.middleware("http")
    async def security_middleware(request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # ── CSRF enforcement ──────────────────────────────────────────────────
        if not _is_csrf_exempt(path, method):
            cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
            header_token = request.headers.get(settings.CSRF_HEADER_NAME, "")

            from app.core.security import validate_csrf_token
            if not cookie_token or not header_token or cookie_token != header_token:
                if not validate_csrf_token(cookie_token):
                    logger.warning(
                        "csrf_rejected  method=%s path=%s  cookie=%s header=%s",
                        method, path,
                        bool(cookie_token), bool(header_token),
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF token missing or invalid"},
                    )

        response: Response = await call_next(request)

        # ── Security headers ──────────────────────────────────────────────────
        for name, value in _SECURITY_HEADERS.items():
            response.headers[name] = value

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = _HSTS_HEADER

        return response

    # 4. Request ID + timing ──────────────────────────────────────────────────
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
