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


class Availability(StrEnum):
    """Where an item physically is — FANI only styles AVAILABLE items."""

    AVAILABLE = "available"
    IN_LAUNDRY = "in_laundry"
    AT_CLEANERS = "at_cleaners"
    LENT_OUT = "lent_out"


class Condition(StrEnum):
    """Physical wear state of a garment — distinct from Availability (location).

    Ordinal by design: use ``CONDITION_RANK`` for threshold math, not string
    comparison. This is a *soft* styling signal, not a hard gate like
    Availability — a WORN tee is perfectly fine for casual/beach and only
    penalised for formal occasions. The one exception is DAMAGED, which is
    hard-excluded from styling and packing the way an unavailable item is.
    See the occasion×condition design note in project memory.
    """

    NEW = "new"
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    WORN = "worn"
    DAMAGED = "damaged"


# Ordinal ranks for condition threshold math (higher = better). Occasion floors
# and ranking penalties compare against these; DAMAGED (0) is the hard-exclude
# floor. Keep in sync with the Condition enum above.
CONDITION_RANK: dict[str, int] = {
    Condition.NEW: 5,
    Condition.EXCELLENT: 4,
    Condition.GOOD: 3,
    Condition.FAIR: 2,
    Condition.WORN: 1,
    Condition.DAMAGED: 0,
}

# Neutral default for items whose condition was never set (existing rows and
# saves that don't specify one). GOOD passes the formal floor, so an unset
# condition never wrongly demotes an item.
DEFAULT_CONDITION = Condition.GOOD


DEFAULT_CATEGORY = ClosetCategory.UNCATEGORISED

CLOSET_SECTIONS = frozenset(
    {
        "clothing",
        "accessories",
        "shoes",
        "outerwear",
        "dresses",
        "inners",
        "special_occasion",
    }
)
