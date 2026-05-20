"""Aggregate all v1 routers for vision-service."""

from fastapi import APIRouter

from app.api.v1 import vision_pipeline, smart_ingest, health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(vision_pipeline.router)
api_router.include_router(smart_ingest.router)
api_router.include_router(health.router)
