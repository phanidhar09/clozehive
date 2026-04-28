"""
Shared response models and utility schemas.
"""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
    field: Optional[str] = None
