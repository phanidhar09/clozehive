"""Outfit compatibility scoring — "does this *go with* what I own?"

This is deliberately separate from embedding similarity. Embedding similarity
answers "do I already own this" (a near-duplicate: another navy blazer). It does
NOT answer "does this pair well" — a blazer's nearest neighbours are other
blazers, never the chinos it should be worn with. Compatibility is a different
function entirely, scored on human styling signals:

- **Color harmony** — neutral / complementary / analogous / clash (hue-based).
  The single biggest driver of "does this go".
- **Formality match** — don't pair joggers with a silk blazer. Derived from
  occasion tags + fabric + name cues (closet items don't store a formality field).
- **Season / occasion overlap** — flag heavy wool against a summer closet.
- **Category role** — a top pairs with a bottom/shoe/layer, never with another
  top. Same-role items compete; they don't complete an outfit.

Everything here is pure (no DB, no network) so it's cheap to unit-test and call
in a tight loop over the closet. Inputs are plain dicts using the shared garment
schema (``category``, ``color``/``primary_color``, ``pattern``, ``fabric``/
``material``, ``season``/``season_tags``, ``occasion``/``occasion_tags``,
``name``/``subcategory``).
"""

from __future__ import annotations

from typing import Any

# ── Color ─────────────────────────────────────────────────────────────────────

# Tokens that function as neutrals — they pair cleanly with anything. Checked
# before chromatic tokens so "navy blue" reads as the neutral navy, not blue.
_NEUTRAL_TOKENS = (
    "black",
    "white",
    "ivory",
    "cream",
    "off-white",
    "ecru",
    "grey",
    "gray",
    "charcoal",
    "slate",
    "beige",
    "tan",
    "khaki",
    "camel",
    "taupe",
    "stone",
    "sand",
    "nude",
    "navy",
    "brown",
    "chocolate",
    "espresso",
    "denim",  # mid blue but behaves as a neutral
    "silver",
    "gold",
)

# Representative hue (degrees on the colour wheel) for chromatic families.
_CHROMATIC_HUES: dict[str, float] = {
    "crimson": 348,
    "burgundy": 345,
    "maroon": 350,
    "wine": 345,
    "red": 0,
    "rose": 345,
    "pink": 330,
    "fuchsia": 320,
    "magenta": 300,
    "coral": 16,
    "salmon": 10,
    "rust": 18,
    "terracotta": 18,
    "orange": 30,
    "peach": 28,
    "amber": 45,
    "mustard": 50,
    "yellow": 55,
    "lime": 80,
    "olive": 70,
    "green": 120,
    "emerald": 140,
    "mint": 150,
    "teal": 180,
    "turquoise": 175,
    "cyan": 185,
    "sky": 200,
    "blue": 220,
    "cobalt": 220,
    "royal": 225,
    "indigo": 240,
    "purple": 280,
    "violet": 270,
    "lavender": 275,
    "plum": 300,
    "lilac": 285,
}


def color_profile(color: str | None) -> tuple[str, float | None]:
    """Classify a colour string → ("neutral"|"chromatic"|"unknown", hue_or_None)."""
    if not color:
        return ("unknown", None)
    s = color.strip().lower()
    if not s:
        return ("unknown", None)
    for tok in _NEUTRAL_TOKENS:
        if tok in s:
            return ("neutral", None)
    for tok, hue in _CHROMATIC_HUES.items():
        if tok in s:
            return ("chromatic", hue)
    return ("unknown", None)


def _hue_distance(a: float, b: float) -> float:
    """Smallest angular distance between two hues, 0–180."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def color_harmony(color_a: str | None, color_b: str | None) -> tuple[float, str | None]:
    """Score colour pairing 0–1 with a short human reason for notable cases."""
    kind_a, hue_a = color_profile(color_a)
    kind_b, hue_b = color_profile(color_b)

    if kind_a == "unknown" or kind_b == "unknown":
        return (0.6, None)  # don't reward or punish what we can't read
    if kind_a == "neutral" or kind_b == "neutral":
        return (1.0, "neutral colors pair cleanly")

    # Both chromatic.
    assert hue_a is not None and hue_b is not None
    d = _hue_distance(hue_a, hue_b)
    if d <= 25:
        return (0.7, "tonal / monochrome")
    if d <= 45:
        return (0.55, "analogous colors")
    if 150 <= d <= 180:
        return (0.9, "complementary colors")
    if 100 <= d < 150:
        return (0.65, "triadic colors")
    return (0.35, "colors clash")


# ── Formality ─────────────────────────────────────────────────────────────────

# Occasion → formality on a 0 (most casual) – 4 (most formal) scale.
_OCCASION_FORMALITY: dict[str, float] = {
    "formal": 4.0,
    "black tie": 4.0,
    "cocktail": 3.3,
    "business": 3.0,
    "business casual": 2.6,
    "work": 2.8,
    "smart casual": 2.3,
    "date night": 2.3,
    "travel": 1.5,
    "casual": 1.0,
    "everyday": 1.0,
    "weekend": 1.0,
    "athleisure": 0.5,
    "sport": 0.4,
    "gym": 0.3,
    "beach": 0.6,
    "loungewear": 0.3,
}

# Fabric nudges formality up or down.
_FABRIC_ADJ: dict[str, float] = {
    "silk": 1.0,
    "satin": 1.0,
    "wool": 0.7,
    "cashmere": 0.9,
    "leather": 0.4,
    "linen": -0.2,
    "cotton": 0.0,
    "knit": 0.0,
    "polyester": -0.1,
    "synthetic": -0.2,
    "denim": -0.8,
    "fleece": -1.0,
    "jersey": -0.4,
}

# Name / subcategory cues that strongly imply formality.
_NAME_FORMAL = (
    "blazer", "suit", "tuxedo", "trouser", "dress shirt", "oxford", "loafer",
    "heel", "pump", "gown", "sport coat", "tie", "slacks", "chino",
)
_NAME_CASUAL = (
    "hoodie", "jogger", "sweatpant", "sneaker", "t-shirt", "tee", "tank",
    "cargo", "track", "flip-flop", "slipper", "graphic", "legging", "short",
)


def _resolve(item: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = item.get(k)
        if v:
            return v
    return None


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    return []


def formality_level(item: dict[str, Any]) -> float:
    """Estimate an item's formality on a 0–4 scale from occasion + fabric + name."""
    occasions = _as_list(_resolve(item, "occasion_tags", "occasion"))
    occ_scores = [_OCCASION_FORMALITY[o] for o in occasions if o in _OCCASION_FORMALITY]
    base = max(occ_scores) if occ_scores else 1.5  # unknown → mid-casual

    fabric = (str(_resolve(item, "fabric", "material") or "")).lower()
    fabric_adj = next((v for k, v in _FABRIC_ADJ.items() if k in fabric), 0.0)

    name = " ".join(
        str(_resolve(item, k) or "").lower() for k in ("name", "subcategory", "category")
    )
    name_adj = 0.0
    if any(tok in name for tok in _NAME_FORMAL):
        name_adj += 0.6
    if any(tok in name for tok in _NAME_CASUAL):
        name_adj -= 0.6

    return max(0.0, min(4.0, base + fabric_adj + name_adj))


def formality_match(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    """Score how close two items sit in formality (1 = same, 0 = ≥3 levels apart)."""
    fa, fb = formality_level(item_a), formality_level(item_b)
    dist = abs(fa - fb)
    score = 1.0 - min(dist / 3.0, 1.0)
    reason = "formality mismatch" if dist >= 2.0 else None
    return (score, reason)


# ── Season / occasion overlap ─────────────────────────────────────────────────


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def season_overlap(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    sa = set(_as_list(_resolve(item_a, "season_tags", "season")))
    sb = set(_as_list(_resolve(item_b, "season_tags", "season")))
    if not sa or not sb or "all-season" in sa or "all-season" in sb:
        return (1.0, None)
    if sa & sb:
        return (1.0, None)
    return (0.3, "season mismatch")


def occasion_overlap(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    oa = set(_as_list(_resolve(item_a, "occasion_tags", "occasion")))
    ob = set(_as_list(_resolve(item_b, "occasion_tags", "occasion")))
    if not oa or not ob:
        return (0.7, None)
    return (0.4 + 0.6 * _jaccard(oa, ob), None)


# ── Category role ─────────────────────────────────────────────────────────────

_CATEGORY_ROLE: dict[str, str] = {
    "tops": "top",
    "top": "top",
    "shirts": "top",
    "bottoms": "bottom",
    "bottom": "bottom",
    "pants": "bottom",
    "dresses": "onepiece",
    "dress": "onepiece",
    "outerwear": "layer",
    "jackets": "layer",
    "shoes": "shoe",
    "footwear": "shoe",
    "accessories": "accessory",
    "accessory": "accessory",
    "bags": "accessory",
}


def category_role(category: str | None) -> str:
    if not category:
        return "other"
    return _CATEGORY_ROLE.get(category.strip().lower(), "other")


# Unordered role pairs that form part of the same outfit (complete, not compete).
_PAIRABLE_ROLES: frozenset[frozenset[str]] = frozenset(
    frozenset(p)
    for p in (
        ("top", "bottom"),
        ("top", "shoe"),
        ("top", "layer"),
        ("top", "accessory"),
        ("bottom", "shoe"),
        ("bottom", "layer"),
        ("bottom", "accessory"),
        ("onepiece", "layer"),
        ("onepiece", "shoe"),
        ("onepiece", "accessory"),
        ("layer", "shoe"),
        ("layer", "accessory"),
        ("shoe", "accessory"),
        ("accessory", "accessory"),  # belt + watch, etc.
    )
)


def roles_pair(role_a: str, role_b: str) -> bool:
    """True when the two roles belong together in one outfit (vs. competing)."""
    if "other" in (role_a, role_b):
        # Unknown role: only safe to treat accessories-as-anything; otherwise
        # don't claim a pairing we can't justify.
        return "accessory" in (role_a, role_b)
    return frozenset((role_a, role_b)) in _PAIRABLE_ROLES


# ── Fused compatibility ───────────────────────────────────────────────────────

_WEIGHTS = {
    "color": 0.40,
    "formality": 0.30,
    "season": 0.15,
    "occasion": 0.15,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9

# A pairing at/above this fused score is considered a genuine "this goes".
PAIR_THRESHOLD = 0.62


def score_compatibility(item_a: dict[str, Any], item_b: dict[str, Any]) -> dict[str, Any]:
    """Score whether ``item_a`` and ``item_b`` go together in one outfit.

    Returns ``{pairs, role_compatible, score, breakdown, reasons}``:
    - ``role_compatible``: do the categories belong in the same outfit at all
      (a top + a bottom, not two tops).
    - ``score``: fused 0–1 styling compatibility.
    - ``pairs``: role_compatible AND score ≥ PAIR_THRESHOLD — a real match.
    """
    role_a = category_role(_resolve(item_a, "category"))
    role_b = category_role(_resolve(item_b, "category"))
    role_ok = roles_pair(role_a, role_b)

    color_a = _resolve(item_a, "primary_color", "color")
    color_b = _resolve(item_b, "primary_color", "color")
    color_s, color_r = color_harmony(color_a, color_b)
    form_s, form_r = formality_match(item_a, item_b)
    seas_s, seas_r = season_overlap(item_a, item_b)
    occ_s, occ_r = occasion_overlap(item_a, item_b)

    score = (
        _WEIGHTS["color"] * color_s
        + _WEIGHTS["formality"] * form_s
        + _WEIGHTS["season"] * seas_s
        + _WEIGHTS["occasion"] * occ_s
    )

    reasons = [r for r in (color_r, form_r, seas_r, occ_r) if r]

    return {
        "role_compatible": role_ok,
        "pairs": role_ok and score >= PAIR_THRESHOLD,
        "score": round(score, 3),
        "breakdown": {
            "color": round(color_s, 3),
            "formality": round(form_s, 3),
            "season": round(seas_s, 3),
            "occasion": round(occ_s, 3),
        },
        "reasons": reasons,
        "roles": [role_a, role_b],
    }
