"""Health check endpoints for vision-service."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "ok", "service": "vision-service"})


@router.get("/live")
async def live() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "live", "service": "vision-service"})
