"""Aggregate all v1 domain routers."""

from fastapi import APIRouter

from app.api.v1.identity.router import router as identity_router
from app.api.v1.wardrobe.router import router as wardrobe_router
from app.api.v1.travel.router import router as travel_router
from app.api.v1.intelligence.router import router as intelligence_router
from app.api.v1.platform.router import router as platform_router
# from app.api.v1.social.router import router as social_router  # Non-MVP: Phase 2

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(identity_router)
api_router.include_router(wardrobe_router)
api_router.include_router(travel_router)
api_router.include_router(intelligence_router)
api_router.include_router(platform_router)
# api_router.include_router(social_router)
