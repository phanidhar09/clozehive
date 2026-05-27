"""Aggregate all v1 routers."""

from fastapi import APIRouter

from app.api.v1 import (
    admin, ai, ai_chat, analytics, auth, closet, health, outfits, profile,
    trips, weather,
    fashion_rag, outfit_history, packing_memory, purchase_gaps, closet_similarity,
    rag, ws, shopping_check,
)
# from app.api.v1 import social  # Non-MVP: re-enable for Phase 2 social features

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(closet.router)
api_router.include_router(outfits.router)
api_router.include_router(outfit_history.router)        # RAG: outfit history
api_router.include_router(trips.router)
api_router.include_router(packing_memory.router)        # RAG: packing memory (trip prefix)
api_router.include_router(analytics.router)
api_router.include_router(ai.router)
api_router.include_router(ai_chat.router)         # AI Stylist Chat
api_router.include_router(weather.router)
api_router.include_router(admin.router)
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(closet_similarity.router)     # RAG: closet similarity
api_router.include_router(fashion_rag.router)           # RAG: fashion knowledge
api_router.include_router(purchase_gaps.router)         # RAG: purchase gaps
api_router.include_router(rag.router)                   # RAG: unified /rag/* endpoints
api_router.include_router(ws.router)                    # Real-time WebSocket notifications
api_router.include_router(shopping_check.router)        # Shopping: in-store buy advisor
# api_router.include_router(social.router)  # Non-MVP: re-enable for Phase 2 social features
