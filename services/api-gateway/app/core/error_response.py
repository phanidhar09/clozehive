"""Standard JSON error payloads for API responses."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def request_id_for(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if isinstance(rid, str) and rid.strip():
        return rid
    return str(uuid.uuid4())


def json_error(
    request: Request,
    *,
    detail: str,
    code: str,
    status_code: int,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "detail": detail,
        "code": code,
        "request_id": request_id_for(request),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body)
