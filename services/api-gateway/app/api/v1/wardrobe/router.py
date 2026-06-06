"""Wardrobe domain — closet, outfits, vision ingestion."""

from fastapi import APIRouter

from app.api.v1.wardrobe import (
    closet, closet_similarity, outfit_history, outfits, smart_ingest, vision_pipeline,
)

router = APIRouter()
router.include_router(closet.router)
router.include_router(closet_similarity.router)
router.include_router(outfits.router)
router.include_router(outfit_history.router)
router.include_router(smart_ingest.router)
router.include_router(vision_pipeline.router)
