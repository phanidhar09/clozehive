"""Constraint-priority engine (Phase 5 of the web-intelligence roadmap).

When several context layers stack in an outfit/packing prompt — venue rules,
cultural dress norms, weather, festivals, personal style — they can conflict
("no shorts allowed" vs 38°C heat; festive jewel tones vs a strict business
dress code). This module emits the single arbitration preamble that tells the
model how to resolve them, in strict order:

  1. mandatory  — venue/event dress rules, local modesty & dress norms
  2. weather    — adequate protection from heat / cold / rain
  3. occasion   — festival or event styling
  4. style      — the user's personal style preferences

Pure logic, no I/O. Callers declare which layers are active in their prompt;
the block lists only those tiers and is omitted entirely when fewer than two
are active (nothing to arbitrate). Individual context blocks must NOT carry
their own ranking text — this is the one source of truth for priority.
"""

from __future__ import annotations

_TIER_LINES: tuple[tuple[str, str], ...] = (
    (
        "mandatory",
        "MANDATORY rules — venue/event dress rules and local modesty or dress norms. Never violate these.",
    ),
    (
        "weather",
        "Weather safety — adequate protection from heat, cold, rain, or wind. Never sacrifice this.",
    ),
    (
        "occasion",
        "Festival / occasion styling — dress for the named festival or event.",
    ),
    (
        "style",
        "Personal style — the user's preferences, colours, and fit.",
    ),
)


def build_constraint_priority_block(
    *,
    mandatory: bool = False,
    weather: bool = False,
    occasion: bool = False,
    style: bool = False,
) -> str:
    """Arbitration preamble for the active constraint layers.

    Returns "" when fewer than two layers are active — a single layer needs
    no priority order, and an empty block keeps prompts tight.
    """
    active = {
        "mandatory": mandatory,
        "weather": weather,
        "occasion": occasion,
        "style": style,
    }
    tiers = [(name, text) for name, text in _TIER_LINES if active[name]]
    if len(tiers) < 2:
        return ""

    lines = [
        "[CONSTRAINT PRIORITY]",
        "When the context sections in this prompt conflict, resolve them in this "
        "strict order (1 outranks 2, and so on):",
    ]
    lines += [f"{i}. {text}" for i, (_, text) in enumerate(tiers, 1)]
    lines.append(
        "Prefer choices that satisfy a higher tier while still honouring the lower "
        "ones — drop a lower tier only when no single choice can satisfy both."
    )
    if mandatory and weather:
        lines.append(
            "Example: if shorts are not allowed but the weather is hot, choose "
            "lightweight breathable trousers — satisfying the rule AND the heat, "
            "not abandoning either."
        )
    lines.append("[END CONSTRAINT PRIORITY]")
    return "\n".join(lines)
