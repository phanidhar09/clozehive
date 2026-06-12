"""Static packing tables: category aliases, purpose→category sets, bag-size constraints."""

from __future__ import annotations

from typing import Any

# ── Category aliases ──────────────────────────────────────────────────────────

_CATEGORY_ALIASES: dict[str, list[str]] = {
    "tops":        ["shirt", "top", "tee", "blouse", "sweater", "hoodie", "knitwear", "polo"],
    "bottoms":     ["pant", "jean", "bottom", "short", "skirt", "trouser", "chino", "legging"],
    "shoes":       ["shoe", "sneaker", "boot", "sandal", "loafer", "heel", "trainer", "mule", "slipper"],
    "outerwear":   ["jacket", "coat", "blazer", "cardigan", "trench", "parka", "vest", "overshirt"],
    "dresses":     ["dress", "jumpsuit", "romper", "co-ord"],
    "accessories": ["bag", "hat", "scarf", "belt", "watch", "jewellery", "sunglasses", "cap", "tote"],
    "innerwear":   ["underwear", "bra", "brief", "boxers", "socks", "lingerie"],
}

_PURPOSE_CATEGORIES: dict[str, list[str]] = {
    "business":  ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "leisure":   ["tops", "bottoms", "shoes", "outerwear"],
    "beach":     ["tops", "bottoms", "shoes", "accessories"],
    "formal":    ["tops", "bottoms", "shoes", "outerwear", "accessories"],
    "adventure": ["tops", "bottoms", "shoes", "outerwear"],
    # Default when no activity/purpose is given — versatile everyday coverage.
    "general":   ["tops", "bottoms", "shoes", "outerwear", "accessories"],
}

# ── Bag size constraints ──────────────────────────────────────────────────────

BAG_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "backpack": {
        "max_tops": 3,
        "max_bottoms": 2,
        "max_shoes": 1,
        "max_outerwear": 1,
        "max_accessories": 2,
        "rewear_days": 2,
        "label": "Backpack only",
        "hint": (
            "VERY LIMITED SPACE. Max 2-3 tops, 1-2 bottoms, 1 pair shoes. "
            "Strong rewear strategy essential. Prioritize multi-purpose items only. "
            "Avoid bulky items. Every item must serve 2+ purposes."
        ),
    },
    "carry_on": {
        "max_tops": 5,
        "max_bottoms": 3,
        "max_shoes": 2,
        "max_outerwear": 1,
        "max_accessories": 3,
        "rewear_days": 2,
        "label": "Carry-on suitcase",
        "hint": (
            "Moderate space. Max 4-5 tops, 2-3 bottoms, 1-2 shoes, 1 outerwear piece. "
            "Key items should rewear across 2 days. Pack versatile neutrals."
        ),
    },
    "medium_suitcase": {
        "max_tops": 8,
        "max_bottoms": 4,
        "max_shoes": 3,
        "max_outerwear": 2,
        "max_accessories": 4,
        "rewear_days": 2,
        "label": "Medium suitcase",
        "hint": (
            "Good space. Up to 6-8 tops, 3-4 bottoms, 2-3 shoes. "
            "Some variety allowed. Still suggest rewearing key pieces."
        ),
    },
    "large_suitcase": {
        "max_tops": 12,
        "max_bottoms": 6,
        "max_shoes": 4,
        "max_outerwear": 3,
        "max_accessories": 6,
        "rewear_days": 1,
        "label": "Large suitcase",
        "hint": (
            "Plenty of space. Full outfit variety possible. "
            "Avoid unnecessary duplication but comfort and coverage is priority."
        ),
    },
    "none": {
        "max_tops": 8,
        "max_bottoms": 4,
        "max_shoes": 3,
        "max_outerwear": 2,
        "max_accessories": 4,
        "rewear_days": 2,
        "label": "Not specified",
        "hint": "Pack sensibly for the trip length. Suggest rewearing versatile items.",
    },
}


def _get_bag_constraints(bag_size: str | None) -> dict[str, Any]:
    return BAG_CONSTRAINTS.get(bag_size or "none", BAG_CONSTRAINTS["none"])


def _normalise_category(category: str) -> str:
    cat = category.lower().strip()
    for canonical, aliases in _CATEGORY_ALIASES.items():
        if cat == canonical or any(a in cat for a in aliases):
            return canonical
    return cat
