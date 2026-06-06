"""Platform domain — analytics, admin, health checks, WebSocket hub."""

from fastapi import APIRouter

from app.api.v1.platform import admin, analytics, health, rum, ws

router = APIRouter()
router.include_router(analytics.router)
router.include_router(admin.router)
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(ws.router)
router.include_router(rum.router)
