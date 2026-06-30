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
- **Pattern harmony** — never two loud prints together; print + solid is foolproof.
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

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
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


def _color_harmony(kind_a: str, hue_a: float | None, kind_b: str, hue_b: float | None) -> tuple[float, str | None]:
    """Score colour pairing from already-classified profiles (see ``color_harmony``)."""
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


def color_harmony(color_a: str | None, color_b: str | None) -> tuple[float, str | None]:
    """Score colour pairing 0–1 with a short human reason for notable cases."""
    kind_a, hue_a = color_profile(color_a)
    kind_b, hue_b = color_profile(color_b)
    return _color_harmony(kind_a, hue_a, kind_b, hue_b)


# ── Pattern ───────────────────────────────────────────────────────────────────

# Tokens that mean "no print" — these pair cleanly with any pattern.
_PATTERN_SOLID_TOKENS = ("solid", "plain", "none", "block", "block color", "block colour")

# Loud, high-visual-weight prints. Two of these in one outfit fight for attention.
_PATTERN_BOLD_TOKENS = (
    "floral",
    "plaid",
    "tartan",
    "check",
    "checked",
    "gingham",
    "paisley",
    "animal",
    "leopard",
    "cheetah",
    "zebra",
    "snake",
    "camo",
    "camouflage",
    "graphic",
    "logo",
    "tropical",
    "geometric",
    "polka",
    "polka dot",
    "polka-dot",
    "dot",
    "tie-dye",
    "tie dye",
    "argyle",
    "houndstooth",
    "abstract",
    "printed",
    "print",
)

# Quiet, low-contrast textures/prints — generally safe alongside a bold print and
# tolerable (with care) alongside another subtle one.
_PATTERN_SUBTLE_TOKENS = (
    "stripe",
    "striped",
    "pinstripe",
    "ribbed",
    "rib",
    "melange",
    "heather",
    "heathered",
    "herringbone",
    "marl",
    "textured",
    "knit",
    "cable",
    "windowpane",
)


def pattern_class(pattern: str | None) -> str:
    """Classify a pattern string → "solid" | "subtle" | "bold" | "unknown".

    "solid" and "unknown" both behave as "no clash risk" — we never punish what we
    can't read, and a solid pairs with anything.
    """
    if not pattern:
        return "solid"
    s = pattern.strip().lower()
    if not s or any(tok in s for tok in _PATTERN_SOLID_TOKENS):
        return "solid"
    if any(tok in s for tok in _PATTERN_BOLD_TOKENS):
        return "bold"
    if any(tok in s for tok in _PATTERN_SUBTLE_TOKENS):
        return "subtle"
    return "unknown"


def _pattern_harmony(ca: str, cb: str) -> tuple[float, str | None]:
    """Score how well two already-classified patterns mix (see ``pattern_harmony``)."""
    # A solid (or an unreadable pattern on either side) carries no clash risk.
    if ca in ("solid", "unknown") or cb in ("solid", "unknown"):
        return (1.0, None)
    if ca == "bold" and cb == "bold":
        return (0.4, "two busy patterns compete")
    if ca == "subtle" and cb == "subtle":
        return (0.85, None)
    # One bold, one subtle — a deliberate, low-risk pairing.
    return (0.92, None)


def pattern_harmony(pattern_a: str | None, pattern_b: str | None) -> tuple[float, str | None]:
    """Score how well two patterns mix, 0–1, with a short reason for clashes.

    The classic rule: never put two loud prints together; a print + solid is
    foolproof; mixing a bold print with a quiet texture works; two quiet patterns
    are usually fine but can fight, so they take a small penalty.
    """
    return _pattern_harmony(pattern_class(pattern_a), pattern_class(pattern_b))


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
    "blazer",
    "suit",
    "tuxedo",
    "trouser",
    "dress shirt",
    "oxford",
    "loafer",
    "heel",
    "pump",
    "gown",
    "sport coat",
    "tie",
    "slacks",
    "chino",
)
_NAME_CASUAL = (
    "hoodie",
    "jogger",
    "sweatpant",
    "sneaker",
    "t-shirt",
    "tee",
    "tank",
    "cargo",
    "track",
    "flip-flop",
    "slipper",
    "graphic",
    "legging",
    "short",
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

    name = " ".join(str(_resolve(item, k) or "").lower() for k in ("name", "subcategory", "category"))
    name_adj = 0.0
    if any(tok in name for tok in _NAME_FORMAL):
        name_adj += 0.6
    if any(tok in name for tok in _NAME_CASUAL):
        name_adj -= 0.6

    return max(0.0, min(4.0, base + fabric_adj + name_adj))


def _formality_match(fa: float, fb: float) -> tuple[float, str | None]:
    """Score formality proximity from two already-computed levels."""
    dist = abs(fa - fb)
    score = 1.0 - min(dist / 3.0, 1.0)
    reason = "formality mismatch" if dist >= 2.0 else None
    return (score, reason)


def formality_match(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    """Score how close two items sit in formality (1 = same, 0 = ≥3 levels apart)."""
    return _formality_match(formality_level(item_a), formality_level(item_b))


# ── Season / occasion overlap ─────────────────────────────────────────────────


def _jaccard(a: AbstractSet[str], b: AbstractSet[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _season_overlap(sa: AbstractSet[str], sb: AbstractSet[str]) -> tuple[float, str | None]:
    if not sa or not sb or "all-season" in sa or "all-season" in sb:
        return (1.0, None)
    if sa & sb:
        return (1.0, None)
    return (0.3, "season mismatch")


def season_overlap(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    sa = frozenset(_as_list(_resolve(item_a, "season_tags", "season")))
    sb = frozenset(_as_list(_resolve(item_b, "season_tags", "season")))
    return _season_overlap(sa, sb)


def _occasion_overlap(oa: AbstractSet[str], ob: AbstractSet[str]) -> tuple[float, str | None]:
    if not oa or not ob:
        return (0.7, None)
    return (0.4 + 0.6 * _jaccard(oa, ob), None)


def occasion_overlap(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    oa = frozenset(_as_list(_resolve(item_a, "occasion_tags", "occasion")))
    ob = frozenset(_as_list(_resolve(item_b, "occasion_tags", "occasion")))
    return _occasion_overlap(oa, ob)


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


# ── Fit / silhouette ────────────────────────────────────────────────────────

# Fit maps onto a 3-point *volume* scale. Proportion styling is about balancing
# volume against fit: pair a voluminous piece with a slim one. The combination
# that reads as sloppy is volume + volume (an oversized top AND a baggy bottom),
# never volume + slim — a relaxed top over slim jeans is a textbook balanced look.
_FIT_RELAXED = (
    "relaxed",
    "loose",
    "baggy",
    "wide",
    "wide-leg",
    "wide leg",
    "oversized",
    "oversize",
    "boxy",
    "flowy",
    "billowy",
    "balloon",
)
_FIT_SLIM = (
    "slim",
    "skinny",
    "fitted",
    "tailored",
    "compression",
    "bodycon",
    "tight",
    "cropped",
)
_FIT_REGULAR = ("regular", "straight", "classic", "standard", "true to size")


def fit_volume(fit: str | None) -> int | None:
    """Map a free-text fit onto a volume scale: 0 slim, 1 regular, 2 relaxed, None unknown.

    Relaxed is checked first so "relaxed straight" reads as relaxed; we never
    punish what we can't read (unknown → None → neutral downstream).
    """
    if not fit:
        return None
    s = fit.strip().lower()
    if not s:
        return None
    if any(tok in s for tok in _FIT_RELAXED):
        return 2
    if any(tok in s for tok in _FIT_SLIM):
        return 0
    if any(tok in s for tok in _FIT_REGULAR):
        return 1
    return None


def _silhouette_harmony(vol_a: int | None, vol_b: int | None) -> tuple[float, str | None]:
    """Score the proportion of two volumes (see ``silhouette_harmony``).

    Balance theory: contrast is the goal. Volume + volume is the only real demerit;
    head-to-toe slim is clean but can read severe, so it takes a tiny nudge.
    """
    if vol_a is None or vol_b is None:
        return (1.0, None)  # unknown fit on either side → neutral
    hi, lo = max(vol_a, vol_b), min(vol_a, vol_b)
    if lo == 2:  # both relaxed/oversized
        return (0.6, "both pieces oversized — shapeless silhouette")
    if hi == 0:  # both slim
        return (0.95, None)
    return (1.0, None)  # any contrast (incl. relaxed + slim) is balanced


def silhouette_harmony(item_a: dict[str, Any], item_b: dict[str, Any]) -> tuple[float, str | None]:
    """Score the fit proportion of two items, 0–1, with a reason for a clash.

    Only meaningful for a top + bottom pairing — proportion balance has no bearing
    on, say, a top and its shoes — so every other role combination is neutral (1.0).
    """
    fa, fb = prepare(item_a), prepare(item_b)
    if {fa.role, fb.role} != {"top", "bottom"}:
        return (1.0, None)
    return _silhouette_harmony(fa.fit_volume, fb.fit_volume)


# ── Fused compatibility ───────────────────────────────────────────────────────

_WEIGHTS = {
    "color": 0.40,
    "formality": 0.30,
    "season": 0.15,
    "occasion": 0.15,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9

# Pattern is a penalty, not a reward dimension: a plain outfit isn't *better* for
# having no print, but two loud prints together is a real demerit. So it scales
# the fused score down on a clash and leaves everything else untouched. This
# fraction caps how much a total pattern clash can cut the score.
_PATTERN_PENALTY_WEIGHT = 0.30

# Silhouette/fit is also a penalty, not a reward dimension (same rationale as
# pattern): a balanced proportion isn't *better*, but a volume-on-volume top+bottom
# is a real demerit. Soft by design — it nudges, never excludes — so a bad-fit pair
# can still surface when color/formality are strong. Caps the worst-case cut.
_SILHOUETTE_PENALTY_WEIGHT = 0.30

# A pairing at/above this fused score is considered a genuine "this goes".
PAIR_THRESHOLD = 0.62


@dataclass(frozen=True)
class ItemFeatures:
    """An item's styling attributes, parsed once for reuse across many pairings.

    Building outfits scores the same item against many partners in tight loops, so
    deriving role / colour / formality / pattern / season / occasion here once —
    instead of re-parsing the raw dict on every ``score_compatibility`` call — is
    the single biggest per-request CPU saving in the builder. Call ``prepare`` once
    per item, then ``score_prepared`` for each pairing.
    """

    role: str
    color_kind: str
    color_hue: float | None
    formality: float
    pattern: str
    seasons: frozenset[str]
    occasions: frozenset[str]
    fit_volume: int | None


def prepare(item: dict[str, Any]) -> ItemFeatures:
    """Parse an item's styling attributes once so pairwise scoring stays cheap."""
    kind, hue = color_profile(_resolve(item, "primary_color", "color"))
    return ItemFeatures(
        role=category_role(_resolve(item, "category")),
        color_kind=kind,
        color_hue=hue,
        formality=formality_level(item),
        pattern=pattern_class(_resolve(item, "pattern")),
        seasons=frozenset(_as_list(_resolve(item, "season_tags", "season"))),
        occasions=frozenset(_as_list(_resolve(item, "occasion_tags", "occasion"))),
        fit_volume=fit_volume(_resolve(item, "fit")),
    )


def score_prepared(fa: ItemFeatures, fb: ItemFeatures) -> dict[str, Any]:
    """Score two already-prepared items — the cheap inner core of ``score_compatibility``."""
    role_ok = roles_pair(fa.role, fb.role)

    color_s, color_r = _color_harmony(fa.color_kind, fa.color_hue, fb.color_kind, fb.color_hue)
    form_s, form_r = _formality_match(fa.formality, fb.formality)
    patt_s, patt_r = _pattern_harmony(fa.pattern, fb.pattern)
    seas_s, seas_r = _season_overlap(fa.seasons, fb.seasons)
    occ_s, occ_r = _occasion_overlap(fa.occasions, fb.occasions)
    # Proportion only applies to a top + bottom pairing; neutral elsewhere.
    if {fa.role, fb.role} == {"top", "bottom"}:
        sil_s, sil_r = _silhouette_harmony(fa.fit_volume, fb.fit_volume)
    else:
        sil_s, sil_r = 1.0, None

    base_score = (
        _WEIGHTS["color"] * color_s
        + _WEIGHTS["formality"] * form_s
        + _WEIGHTS["season"] * seas_s
        + _WEIGHTS["occasion"] * occ_s
    )
    # Apply pattern and silhouette as multiplicative penalties: a clash drags the
    # whole pairing down, a clean combination passes through unchanged.
    pattern_penalty = 1.0 - _PATTERN_PENALTY_WEIGHT * (1.0 - patt_s)
    silhouette_penalty = 1.0 - _SILHOUETTE_PENALTY_WEIGHT * (1.0 - sil_s)
    score = base_score * pattern_penalty * silhouette_penalty

    reasons = [r for r in (color_r, form_r, patt_r, seas_r, occ_r, sil_r) if r]

    return {
        "role_compatible": role_ok,
        "pairs": role_ok and score >= PAIR_THRESHOLD,
        "score": round(score, 3),
        "breakdown": {
            "color": round(color_s, 3),
            "formality": round(form_s, 3),
            "pattern": round(patt_s, 3),
            "season": round(seas_s, 3),
            "occasion": round(occ_s, 3),
            "silhouette": round(sil_s, 3),
        },
        "reasons": reasons,
        "roles": [fa.role, fb.role],
    }


def score_compatibility(item_a: dict[str, Any], item_b: dict[str, Any]) -> dict[str, Any]:
    """Score whether ``item_a`` and ``item_b`` go together in one outfit.

    Returns ``{pairs, role_compatible, score, breakdown, reasons}``:
    - ``role_compatible``: do the categories belong in the same outfit at all
      (a top + a bottom, not two tops).
    - ``score``: fused 0–1 styling compatibility.
    - ``pairs``: role_compatible AND score ≥ PAIR_THRESHOLD — a real match.

    Convenience wrapper over ``prepare`` + ``score_prepared``. In tight loops over
    a closet, call ``prepare`` once per item and reuse the result instead.
    """
    return score_prepared(prepare(item_a), prepare(item_b))
