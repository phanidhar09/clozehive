"""Aggregate all v1 routers for closet-service.

Owns the wardrobe domain + closet-data-heavy AI features. Authentication is local
JWT validation (shared JWT_SECRET); user account data, when needed, comes from
api-gateway over the internal API seam (see repositories/user_repo.py).

NOTE (dual-stack): during the split these routes are ALSO still served by
api-gateway. nginx cuts traffic over to closet-service in Phase 4.
"""

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    ai_chat,
    analytics,
    closet,
    closet_similarity,
    fashion_rag,
    health,
    outfit_history,
    outfits,
    packing_memory,
    purchase_gaps,
    rag,
    shopping_check,
    trips,
)

api_router = APIRouter(prefix="/api/v1")

# Wardrobe core
api_router.include_router(closet.router)
api_router.include_router(outfits.router)
api_router.include_router(trips.router)
api_router.include_router(packing_memory.router)        # trip-prefixed packing
api_router.include_router(analytics.router)

# AI styling
api_router.include_router(ai.router)
api_router.include_router(ai_chat.router)               # AI Stylist Chat
api_router.include_router(shopping_check.router)        # in-store buy advisor

# RAG / similarity
api_router.include_router(closet_similarity.router)
api_router.include_router(fashion_rag.router)
api_router.include_router(outfit_history.router)
api_router.include_router(purchase_gaps.router)
api_router.include_router(rag.router)                   # unified /rag/* endpoints

# Health (also exposed at /health by the app factory)
api_router.include_router(health.router, prefix="/health", tags=["health"])
