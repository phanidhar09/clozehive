"""
Centralized application exceptions.
All domain errors subclass AppError — the global handler turns them into
structured JSON responses with the correct HTTP status code.
No raw stack traces ever reach the client.
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error — always serialised to JSON."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> dict:
        payload: dict = {"error": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


# ── 4xx ──────────────────────────────────────────────────────────────────────

class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"


# ── 5xx ──────────────────────────────────────────────────────────────────────

class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"


class AIServiceError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "AI_SERVICE_ERROR"


# ── FastAPI exception handlers ────────────────────────────────────────────────

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    from app.core.logging import get_logger
    logger = get_logger("exceptions")
    logger.warning(
        "app_error",
        path=str(request.url.path),
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    from app.core.config import get_settings
    from app.core.logging import get_logger
    logger = get_logger("exceptions")
    logger.error(
        "unhandled_error",
        path=str(request.url.path),
        exc_type=type(exc).__name__,
        exc_str=str(exc),
        exc_info=True,
    )
    # Never expose internals in production
    if get_settings().is_production:
        msg = "An unexpected error occurred"
    else:
        msg = str(exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "INTERNAL_ERROR", "message": msg},
    )
