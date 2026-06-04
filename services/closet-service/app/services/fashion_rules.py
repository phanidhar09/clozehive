"""Reusable fashion rules engine for CLOZEHIVE AI Stylist.

All functions are pure / stateless — call them inside the AI prompt builder or
post-process AI output to surface rule violations to the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Colour taxonomy ───────────────────────────────────────────────────────────

_NEUTRALS = {"white", "black", "grey", "gray", "beige", "cream", "navy", "camel", "tan", "khaki"}
_EARTH_TONES = {"brown", "olive", "rust", "terracotta", "burgundy", "mustard", "forest green"}
_PASTELS = {"blush", "lavender", "mint", "baby blue", "peach", "lilac", "powder blue"}
_BOLDS = {"red", "cobalt blue", "hot pink", "neon yellow", "emerald", "royal purple"}

_COMPLEMENTARY: dict[str, set[str]] = {
    "navy": {"white", "grey", "beige", "camel", "light blue", "cream"},
    "black": {"white", "grey", "red", "blush", "camel", "cobalt blue"},
    "white": {"navy", "black", "blue", "pastel", "olive", "tan"},
    "grey": {"white", "black", "navy", "burgundy", "blue"},
    "camel": {"white", "navy", "brown", "olive", "cream"},
    "olive": {"white", "camel", "brown", "rust", "navy"},
    "burgundy": {"grey", "navy", "black", "cream", "camel"},
    "blue": {"white", "grey", "navy", "tan", "camel"},
}

# ── Formality ladder ──────────────────────────────────────────────────────────

_OCCASION_FORMALITY: dict[str, int] = {
    "loungewear": 0,
    "casual": 1,
    "weekend": 1,
    "athleisure": 1,
    "smart casual": 2,
    "business casual": 3,
    "business": 4,
    "office": 4,
    "work": 4,
    "cocktail": 5,
    "dinner": 4,
    "date night": 4,
    "semi formal": 5,
    "formal": 6,
    "black tie": 7,
    "wedding": 6,
    "gala": 7,
}

_CATEGORY_FORMALITY: dict[str, dict[str, int]] = {
    "tops": {
        "t-shirt": 1, "tank top": 1, "polo": 2, "button-down": 3,
        "dress shirt": 5, "blazer": 4, "sweater": 2, "hoodie": 0,
    },
    "bottoms": {
        "joggers": 0, "shorts": 1, "jeans": 2, "chinos": 3,
        "trousers": 4, "dress pants": 5, "slacks": 5,
    },
    "shoes": {
        "sneakers": 1, "slides": 0, "loafers": 3, "boots": 3,
        "oxfords": 5, "heels": 5, "stilettos": 6, "dress shoes": 5,
    },
}

# ── Weather suitability ───────────────────────────────────────────────────────

_WEATHER_FABRIC_MAP: dict[str, list[str]] = {
    "hot": ["cotton", "linen", "rayon", "chambray"],
    "warm": ["cotton", "jersey", "silk", "light wool"],
    "mild": ["cotton", "wool", "denim", "polyester"],
    "cool": ["wool", "denim", "cashmere", "flannel", "corduroy"],
    "cold": ["wool", "cashmere", "down", "fleece", "thermal", "leather"],
    "rainy": ["waterproof", "nylon", "gore-tex", "polyester"],
}

_WEATHER_CATEGORY_AVOID: dict[str, list[str]] = {
    "hot": ["outerwear"],
    "cold": ["shorts", "sleeveless"],
    "rainy": ["suede", "canvas sneakers"],
}

# ── Pattern mixing rules ──────────────────────────────────────────────────────

_CLASHING_PATTERNS = [
    {"stripes", "plaid"},
    {"floral", "animal print"},
    {"plaid", "houndstooth"},
    {"polka dots", "stripes"},
]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FashionRuleViolation:
    rule: str
    severity: str  # "warning" | "error"
    message: str


@dataclass
class FashionRuleResult:
    violations: list[FashionRuleViolation] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    penalty_score: int = 0  # subtract from matching score


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise(s: str | None) -> str:
    return (s or "").strip().lower()


def _colour_family(colour: str) -> str:
    c = _normalise(colour)
    if c in _NEUTRALS:
        return "neutral"
    if c in _EARTH_TONES:
        return "earth"
    if c in _PASTELS:
        return "pastel"
    if c in _BOLDS:
        return "bold"
    return "other"


# ── Individual rule checks ────────────────────────────────────────────────────

def check_color_harmony(items: list[dict[str, Any]]) -> FashionRuleResult:
    result = FashionRuleResult(rules_applied=["color_harmony"])
    colours = [_normalise(i.get("color")) for i in items if i.get("color")]
    if len(colours) < 2:
        return result

    families = [_colour_family(c) for c in colours]
    bold_count = families.count("bold")
    neutral_count = families.count("neutral")

    if bold_count >= 3:
        result.violations.append(FashionRuleViolation(
            rule="color_harmony",
            severity="warning",
            message="Three or more bold colours create visual noise — anchor with a neutral.",
        ))
        result.penalty_score += 5
    elif bold_count == 2 and neutral_count == 0:
        result.violations.append(FashionRuleViolation(
            rule="color_harmony",
            severity="warning",
            message="Two bold colours compete without a neutral to balance them.",
        ))
        result.penalty_score += 3

    for i, c1 in enumerate(colours):
        for c2 in colours[i + 1 :]:
            if c1 in _COMPLEMENTARY and c2 not in _COMPLEMENTARY.get(c1, set()):
                if _colour_family(c1) != "neutral" and _colour_family(c2) != "neutral":
                    result.tips.append(
                        f"'{c1.title()}' and '{c2.title()}' may clash — consider a neutral separator."
                    )
                    break

    if not result.violations:
        result.tips.append("Colour palette is well balanced.")
    return result


def check_occasion_formality(
    items: list[dict[str, Any]], occasion: str
) -> FashionRuleResult:
    result = FashionRuleResult(rules_applied=["occasion_formality"])
    occ_lvl = _OCCASION_FORMALITY.get(_normalise(occasion), 2)

    for item in items:
        cat = _normalise(item.get("category"))
        name = _normalise(item.get("name"))
        for cat_key, name_map in _CATEGORY_FORMALITY.items():
            if cat_key in cat:
                for name_key, lvl in name_map.items():
                    if name_key in name:
                        diff = abs(lvl - occ_lvl)
                        if diff >= 3:
                            result.violations.append(FashionRuleViolation(
                                rule="occasion_formality",
                                severity="warning",
                                message=(
                                    f"'{item.get('name')}' (formality {lvl}) "
                                    f"is mismatched for a {occasion} occasion (formality {occ_lvl})."
                                ),
                            ))
                            result.penalty_score += 4
    if not result.violations:
        result.tips.append(f"All items are appropriate for a {occasion} setting.")
    return result


def check_weather_suitability(
    items: list[dict[str, Any]], weather_condition: str
) -> FashionRuleResult:
    result = FashionRuleResult(rules_applied=["weather_suitability"])
    cond = _normalise(weather_condition)
    suitable_fabrics = _WEATHER_FABRIC_MAP.get(cond, [])
    avoid_categories = _WEATHER_CATEGORY_AVOID.get(cond, [])

    for item in items:
        fabric = _normalise(item.get("fabric"))
        cat = _normalise(item.get("category"))

        if fabric and suitable_fabrics and not any(f in fabric for f in suitable_fabrics):
            result.tips.append(
                f"'{item.get('name')}' ({fabric}) may not be ideal for {cond} weather."
            )

        if avoid_categories and any(a in cat for a in avoid_categories):
            result.violations.append(FashionRuleViolation(
                rule="weather_suitability",
                severity="warning",
                message=f"'{item.get('name')}' is not ideal for {cond} conditions.",
            ))
            result.penalty_score += 3

    if not result.violations and not result.tips:
        result.tips.append(f"Outfit is well suited for {cond} weather.")
    return result


def check_pattern_balance(items: list[dict[str, Any]]) -> FashionRuleResult:
    result = FashionRuleResult(rules_applied=["pattern_balance"])
    patterns = [_normalise(i.get("pattern")) for i in items if i.get("pattern") and i.get("pattern") != "solid"]

    if len(patterns) >= 3:
        result.violations.append(FashionRuleViolation(
            rule="pattern_balance",
            severity="warning",
            message="Three or more patterns create visual clutter — simplify to one or two.",
        ))
        result.penalty_score += 4

    pattern_set = set(patterns)
    for clash_pair in _CLASHING_PATTERNS:
        if clash_pair.issubset(pattern_set):
            result.violations.append(FashionRuleViolation(
                rule="pattern_balance",
                severity="error",
                message=f"{' and '.join(clash_pair).title()} patterns clash — avoid mixing them.",
            ))
            result.penalty_score += 6

    if not result.violations:
        if len(patterns) == 0:
            result.tips.append("Solid palette creates a clean, versatile look.")
        elif len(patterns) == 1:
            result.tips.append("One statement pattern keeps the outfit focused.")
    return result


def check_layering_logic(items: list[dict[str, Any]]) -> FashionRuleResult:
    result = FashionRuleResult(rules_applied=["layering_logic"])
    has_outerwear = any("outerwear" in _normalise(i.get("category")) for i in items)
    has_top = any(_normalise(i.get("category")) in ("tops", "shirts") for i in items)

    if has_outerwear and not has_top:
        result.violations.append(FashionRuleViolation(
            rule="layering_logic",
            severity="warning",
            message="Outerwear without a base top — add an inner layer for a complete look.",
        ))
        result.penalty_score += 3

    return result


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_outfit(
    items: list[dict[str, Any]],
    occasion: str = "casual",
    weather_condition: str = "mild",
    user_profile: dict[str, Any] | None = None,
) -> FashionRuleResult:
    """Run all fashion rule checks and aggregate results."""
    aggregated = FashionRuleResult()

    for checker in [
        lambda: check_color_harmony(items),
        lambda: check_occasion_formality(items, occasion),
        lambda: check_weather_suitability(items, weather_condition),
        lambda: check_pattern_balance(items),
        lambda: check_layering_logic(items),
    ]:
        result = checker()
        aggregated.violations.extend(result.violations)
        aggregated.tips.extend(result.tips)
        aggregated.rules_applied.extend(result.rules_applied)
        aggregated.penalty_score += result.penalty_score

    # Respect user colour avoidances from style profile
    if user_profile:
        avoided = [_normalise(c) for c in (user_profile.get("avoided_colors") or [])]
        for item in items:
            colour = _normalise(item.get("color"))
            if colour and colour in avoided:
                aggregated.violations.append(FashionRuleViolation(
                    rule="user_preference",
                    severity="warning",
                    message=f"'{item.get('name')}' is {colour} — a colour in your avoid list.",
                ))
                aggregated.penalty_score += 2

    return aggregated


def build_fashion_rules_prompt_block(
    items: list[dict[str, Any]],
    occasion: str = "casual",
    weather_condition: str = "mild",
    user_profile: dict[str, Any] | None = None,
) -> str:
    """Return a compact string block summarising rule results for injection into AI prompts."""
    res = evaluate_outfit(items, occasion, weather_condition, user_profile)

    lines = ["[FASHION RULES ANALYSIS]"]
    if res.violations:
        lines.append("Potential issues:")
        for v in res.violations:
            lines.append(f"  [{v.severity.upper()}] {v.message}")
    if res.tips:
        lines.append("Styling notes:")
        for t in res.tips:
            lines.append(f"  • {t}")
    lines.append(f"Rules applied: {', '.join(res.rules_applied)}")
    lines.append("[END FASHION RULES]")
    return "\n".join(lines)
