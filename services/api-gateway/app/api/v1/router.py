"""Aggregate all v1 routers."""

from fastapi import APIRouter

from app.api.v1 import admin, ai, analytics, auth, closet, health, outfits, smart_ingest, trips, vision_pipeline, weather
# from app.api.v1 import social  # Non-MVP: re-enable for Phase 2 social features
# from app.api.v1 import ws     # Non-MVP: re-enable for Phase 2 real-time notifications

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(closet.router)
api_router.include_router(outfits.router)
api_router.include_router(trips.router)
api_router.include_router(analytics.router)
api_router.include_router(ai.router)
api_router.include_router(weather.router)
api_router.include_router(admin.router)
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(smart_ingest.router, prefix="/closet")
api_router.include_router(vision_pipeline.router, prefix="/closet")
# api_router.include_router(social.router)  # Non-MVP: re-enable for Phase 2 social features
# api_router.include_router(ws.router)      # Non-MVP: re-enable for Phase 2 real-time notifications
