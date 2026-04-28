"""
Closet item schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ClosetItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=60)
    color: Optional[str] = Field(None, max_length=60)
    brand: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None
    image_url: Optional[str] = Field(None, max_length=512)
    notes: Optional[str] = None


class ClosetItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, min_length=1, max_length=60)
    color: Optional[str] = None
    brand: Optional[str] = None
    tags: Optional[List[str]] = None
    image_url: Optional[str] = None
    notes: Optional[str] = None


class ClosetItemResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    category: str
    color: Optional[str] = None
    brand: Optional[str] = None
    tags: List[str] = []
    image_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
