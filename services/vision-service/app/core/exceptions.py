"""
Centralized application exceptions for vision-service.
"""

from __future__ import annotations


from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.error_response import json_error


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
    human = exc.detail if exc.detail else exc.message
    return json_error(
        request,
        detail=human,
        code=exc.code,
        status_code=exc.status_code,
    )


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
    if get_settings().is_production:
        msg = "An unexpected error occurred"
    else:
        msg = str(exc)

    return json_error(
        request,
        detail=msg,
        code="INTERNAL_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    from app.core.logging import get_logger
    logger = get_logger("exceptions")
    detail = exc.detail
    if isinstance(detail, list):
        human = "Validation failed"
    elif isinstance(detail, dict):
        human = str(detail.get("detail") or detail.get("message") or detail)
    else:
        human = str(detail)
    code_map = {
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    logger.warning(
        "http_exception",
        path=str(request.url.path),
        status_code=exc.status_code,
        code=code,
    )
    extra = {}
    if isinstance(detail, dict) and detail:
        extra["errors"] = detail
    return json_error(
        request,
        detail=human,
        code=code,
        status_code=exc.status_code,
        extra=extra if extra else None,
    )
