"""Platform domain — admin, health, WebSocket hub, RUM (always on);
analytics (migrated-routes gate)."""

from fastapi import APIRouter

from app.api.v1.platform import admin, analytics, health, rum, ws
from app.core.config import get_settings

router = APIRouter()
# Gateway-owned platform routers (nginx routes these here).
router.include_router(admin.router)
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(ws.router)
router.include_router(rum.router)

# analytics mounts under the migrated-routes gate.
if get_settings().mount_migrated_routes:
    router.include_router(analytics.router)
