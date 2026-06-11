"""Intelligence domain — AI chat, RAG, shopping advisor, async jobs."""

from fastapi import APIRouter

from app.api.v1.intelligence import (
    ai,
    ai_chat,
    fashion_rag,
    jobs,
    purchase_gaps,
    rag,
    shopping_check,
)

router = APIRouter()
router.include_router(ai.router)
router.include_router(ai_chat.router)
router.include_router(jobs.router)
router.include_router(fashion_rag.router)
router.include_router(purchase_gaps.router)
router.include_router(rag.router)
router.include_router(shopping_check.router)
