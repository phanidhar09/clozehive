"""Aggregate all v1 domain routers.

The wardrobe and intelligence domains were extracted to closet-service. nginx
routes their prefixes (closet, outfits, ai, ai-chat, rag, fashion-knowledge,
purchase-gaps, shopping) to closet-service, so the gateway only mounts its copies
when ``settings.mount_migrated_routes`` is true (dev/test, or explicit override) —
never in production, where closet-service is the sole owner. travel/platform mount
their kept routers (weather, admin, health, ws, rum) unconditionally and gate only
the migrated sub-routers (trips, analytics) internally.
"""

from fastapi import APIRouter

from app.api.v1.identity.router import router as identity_router
from app.api.v1.intelligence.router import router as intelligence_router
from app.api.v1.platform.router import router as platform_router
from app.api.v1.travel.router import router as travel_router
from app.api.v1.wardrobe.router import router as wardrobe_router
from app.core.config import get_settings

# from app.api.v1.social.router import router as social_router  # Non-MVP: Phase 2

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(identity_router)
api_router.include_router(travel_router)
api_router.include_router(platform_router)

# Fully-migrated domains — gateway serves them only outside production.
if get_settings().mount_migrated_routes:
    api_router.include_router(wardrobe_router)
    api_router.include_router(intelligence_router)
# api_router.include_router(social_router)
