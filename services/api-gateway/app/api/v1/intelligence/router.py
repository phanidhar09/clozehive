"""Intelligence domain — AI chat, RAG, shopping advisor."""

from fastapi import APIRouter

from app.api.v1.intelligence import (
    ai,
    ai_chat,
    fashion_rag,
    purchase_gaps,
    rag,
    shopping_check,
    wardrobe_analyst,
)

router = APIRouter()
router.include_router(ai.router)
router.include_router(ai_chat.router)
router.include_router(fashion_rag.router)
router.include_router(purchase_gaps.router)
router.include_router(rag.router)
router.include_router(shopping_check.router)
router.include_router(wardrobe_analyst.router)
