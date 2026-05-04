"""Shared wardrobe taxonomy — avoid magic strings in services and schemas."""

from __future__ import annotations

from enum import StrEnum


class ClosetCategory(StrEnum):
    TOPS = "tops"
    BOTTOMS = "bottoms"
    SHOES = "shoes"
    OUTERWEAR = "outerwear"
    DRESSES = "dresses"
    ACCESSORIES = "accessories"
    UNCATEGORISED = "uncategorised"


class Season(StrEnum):
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"
    ALL_SEASON = "all-season"


class Occasion(StrEnum):
    CASUAL = "casual"
    BUSINESS = "business"
    FORMAL = "formal"
    SPORT = "sport"
    BEACH = "beach"
    DATE_NIGHT = "date-night"


DEFAULT_CATEGORY = ClosetCategory.UNCATEGORISED

CLOSET_SECTIONS = frozenset({
    "clothing",
    "accessories",
    "shoes",
    "outerwear",
    "dresses",
    "inners",
    "special_occasion",
})
