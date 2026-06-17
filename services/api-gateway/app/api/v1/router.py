"""Aggregate all v1 domain routers.

The gateway is the sole owner of the wardrobe and intelligence domains (closet,
outfits, ai, ai-chat, rag, fashion-knowledge, purchase-gaps, shopping). Those
routers mount when ``settings.mount_migrated_routes`` is true — which is dev/test
by default, and production via the explicit ``SERVE_MIGRATED_DOMAIN_ROUTES=true``
override (see render.yaml). The flag defaults off in production purely as a
safety interlock; there is no separate service to fall back to. travel/platform
mount their routers (weather, trips, admin, health, ws, rum) unconditionally.
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
