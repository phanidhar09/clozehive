"""Deterministic claim-grounding for AI reply prose.

The ID-based validator (:mod:`app.core.ai_output_validator`) grounds *outfit
items*; this module grounds the free-text ``reply`` around them. Two families
of checks, both pure functions (no I/O, no LLM):

**Provenance checks** — a claim *type* requires the matching context to have
been provided this turn. If the reply cites a forecast but no weather context
was fetched, references "yesterday" on a first turn, quotes a user preference
with no profile loaded, or describes "your uploaded photo" when no image was
attached, the claim is definitionally ungrounded — no fact-checking needed.

**Closet-record checks** — where the model names an *owned* item (matched by
its head noun), the claimed colour / material / brand is compared against the
authoritative closet record. Claims about items the user doesn't own are left
alone (they're usually suggestions), so false positives stay rare.

Callers get a list of :class:`ClaimViolation` and can redact the offending
sentences (:func:`redact_ungrounded_claims`) before persisting, or surface a
``correction`` event on the streaming path where the text already shipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

logger = get_logger("claim_grounding")

# ── Context the caller provides ───────────────────────────────────────────────


@dataclass(frozen=True)
class GroundingContext:
    """What context was actually supplied to the model this turn."""

    weather_provided: bool = False
    history_depth: int = 0
    profile_provided: bool = False
    images_provided: bool = False
    current_month: int | None = None  # 1–12; enables season checks


@dataclass
class ClaimViolation:
    kind: str
    detail: str
    sentence: str = ""


# ── Vocabulary ────────────────────────────────────────────────────────────────

_COLORS = (
    "black|white|grey|gray|navy|blue|red|green|yellow|orange|purple|pink|brown|"
    "beige|cream|tan|burgundy|maroon|olive|teal|turquoise|gold|silver|khaki|"
    "charcoal|ivory|lavender|mustard|coral|emerald|mint|rust|plum|magenta|"
    "indigo|violet|scarlet|crimson"
)
_COLOR_SET = set(_COLORS.split("|"))

_MATERIALS = (
    "silk|cotton|wool|linen|leather|denim|suede|cashmere|polyester|nylon|velvet|"
    "satin|chiffon|tweed|corduroy|fleece|canvas|jersey|waterproof|windproof|insulated"
)
_MATERIAL_SET = set(_MATERIALS.split("|"))

# Words that look like proper nouns but are never brands.
_NOT_BRANDS = (
    {
        "your",
        "the",
        "a",
        "an",
        "my",
        "this",
        "that",
        "these",
        "those",
        "i",
        "we",
        "it",
        "its",
        "his",
        "her",
        "their",
        "our",
        "some",
        "any",
    }
    | _COLOR_SET
    | _MATERIAL_SET
)

# Category synonym map for ownership claims ("you have no trousers" while the
# closet holds chinos). Deliberately small — only unambiguous garment families.
_CATEGORY_SYNONYMS: dict[str, set[str]] = {
    "trousers": {"trousers", "pants", "chinos", "jeans", "slacks", "leggings"},
    "pants": {"trousers", "pants", "chinos", "jeans", "slacks", "leggings"},
    "shoes": {"shoes", "sneakers", "trainers", "boots", "loafers", "heels", "sandals"},
    "sneakers": {"sneakers", "trainers"},
    "tops": {"tops", "shirt", "shirts", "blouse", "tee", "t-shirt", "sweater"},
    "outerwear": {"outerwear", "jacket", "coat", "blazer", "parka"},
}

# ── Provenance claim patterns ─────────────────────────────────────────────────

_WEATHER_CLAIM = re.compile(
    r"""(?ix)
    \d+\s*° |
    \b\d+\s*degrees\b |
    \bforecast\b |
    \bit(?:'s|\s+is|\s+will\s+be)\s+(?:freezing|cold|hot|warm|chilly|raining|rainy|sunny|snowing|humid|windy)\b |
    \btomorrow\s+will\s+be\b
    """,
)
_MEMORY_CLAIM = re.compile(
    r"""(?ix)
    \byesterday\b |
    \blast\s+(?:time|week|chat|conversation)\b |
    \byou\s+asked\s+(?:about|me|for)\b |
    \bas\s+we\s+discussed\b |
    \bearlier\s+you\b |
    \bpreviously\s+you\b
    """,
)
_PREFERENCE_CLAIM = re.compile(
    r"""(?ix)
    \byou\s+(?:told\s+me|said|mentioned)\b |
    \b(?:since|because|as)\s+you\s+(?:hate|love|prefer|dislike|avoid)\b |
    \byou\s+(?:hate|love|prefer|dislike)\b |
    \b(?:as\s+)?you\s+wear\s+a\s+size\b |
    \byour\s+size\s+\d+\b
    """,
)
_IMAGE_CLAIM = re.compile(
    r"""(?ix)
    \byour?\s+(?:uploaded|attached)\b |
    \bin\s+(?:the|your)\s+(?:photo|picture|image)\b |
    \byou\s+uploaded\b
    """,
)
_OWNERSHIP_POSITIVE = re.compile(
    r"(?i)\byou\s+(?:already\s+)?(?:own|have)\s+(?:a|an|the|some|two|three|four|five|several|many|\d+)\s+((?:[\w-]+\s+){0,2}[\w-]+)"
)
_OWNERSHIP_NEGATIVE = re.compile(r"(?i)\byou\s+(?:have\s+no|don'?t\s+(?:own|have)\s+any)\s+((?:[\w-]+\s+){0,2}[\w-]+)")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


# ── Closet indexing helpers ───────────────────────────────────────────────────


def _head_noun(name: str) -> str:
    tokens = re.findall(r"[a-z]+", (name or "").lower())
    return tokens[-1] if tokens else ""


def _closet_index(closet_map: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """head-noun → owned items with that head noun."""
    index: dict[str, list[dict[str, Any]]] = {}
    for item in (closet_map or {}).values():
        head = _head_noun(str(item.get("name") or ""))
        if len(head) > 2:
            index.setdefault(head, []).append(item)
    return index


def _closet_tokens(closet_map: dict[str, dict[str, Any]]) -> set[str]:
    tokens: set[str] = set()
    for item in (closet_map or {}).values():
        for f in ("name", "category"):
            tokens.update(re.findall(r"[a-z]+", str(item.get(f) or "").lower()))
    return tokens


def _item_vocab(item: dict[str, Any]) -> set[str]:
    """All words legitimately attributable to an item (name, color, fabric, tags)."""
    words: set[str] = set()
    for f in ("name", "color", "fabric", "pattern"):
        words.update(re.findall(r"[a-z]+", str(item.get(f) or "").lower()))
    for tag in item.get("tags") or []:
        words.update(re.findall(r"[a-z]+", str(tag).lower()))
    return words


# ── The audit ─────────────────────────────────────────────────────────────────


def audit_reply_claims(
    reply: str | None,
    closet_map: dict[str, dict[str, Any]],
    ctx: GroundingContext,
) -> list[ClaimViolation]:
    """Return every ungrounded claim found in *reply*. Empty list == clean."""
    text = str(reply or "")
    if not text.strip():
        return []

    violations: list[ClaimViolation] = []
    index = _closet_index(closet_map)
    owned_tokens = _closet_tokens(closet_map)

    for sentence in _SENTENCE_SPLIT.split(text):
        low = sentence.lower()

        # ── Provenance: claim type requires matching context ────────────────
        if not ctx.weather_provided and _WEATHER_CLAIM.search(sentence):
            violations.append(
                ClaimViolation("weather_unprovenanced", "weather claim without weather context", sentence)
            )
        if ctx.history_depth == 0 and _MEMORY_CLAIM.search(sentence):
            violations.append(
                ClaimViolation("memory_unprovenanced", "references prior conversation on first turn", sentence)
            )
        if not ctx.profile_provided and _PREFERENCE_CLAIM.search(sentence):
            violations.append(
                ClaimViolation("preference_unprovenanced", "quotes a user preference with no profile", sentence)
            )
        if not ctx.images_provided and _IMAGE_CLAIM.search(sentence):
            violations.append(ClaimViolation("image_unprovenanced", "references an image none was attached", sentence))

        # ── Ownership claims vs the actual closet ───────────────────────────
        for m in _OWNERSHIP_POSITIVE.finditer(sentence):
            claimed = set(re.findall(r"[a-z]+", m.group(1).lower())) - _COLOR_SET
            if claimed and not (claimed & owned_tokens):
                violations.append(
                    ClaimViolation("ownership_unverified", f"claims user owns '{m.group(1)}' — not in closet", sentence)
                )
        for m in _OWNERSHIP_NEGATIVE.finditer(sentence):
            for word in re.findall(r"[a-z]+", m.group(1).lower()):
                synonyms = _CATEGORY_SYNONYMS.get(word, {word})
                if synonyms & owned_tokens:
                    violations.append(
                        ClaimViolation(
                            "ownership_unverified",
                            f"claims user has no '{word}' but closet contains {sorted(synonyms & owned_tokens)}",
                            sentence,
                        )
                    )
                    break

        # ── Colour / material claims about *owned* items ─────────────────────
        for m in re.finditer(rf"\b({_COLORS})\s+([a-z]+)\b", low):
            claimed_color, noun = m.group(1), m.group(2)
            items = index.get(noun) or []
            if len(items) != 1:  # ambiguous or not owned — leave alone
                continue
            if claimed_color not in _item_vocab(items[0]):
                actual = items[0].get("color") or "unrecorded"
                violations.append(
                    ClaimViolation(
                        "color_mismatch",
                        f"calls the {noun} '{claimed_color}' but closet records '{actual}'",
                        sentence,
                    )
                )
        for m in re.finditer(rf"\b({_MATERIALS})\b((?:\s+[a-z]+){{0,3}})", low):
            claimed_mat = m.group(1)
            window = re.findall(r"[a-z]+", m.group(2))
            for noun in window:
                items = index.get(noun) or []
                if len(items) == 1 and claimed_mat not in _item_vocab(items[0]):
                    actual = items[0].get("fabric") or "unrecorded"
                    violations.append(
                        ClaimViolation(
                            "material_mismatch",
                            f"calls the {noun} '{claimed_mat}' but closet records '{actual}'",
                            sentence,
                        )
                    )
                    break

        # ── Brand claims about *owned* items ────────────────────────────────
        # Scan backwards from each owned head noun: capitalised tokens in the
        # preceding 4 words that aren't colours/materials/determiners are a
        # brand attribution — verify against the closet record's vocabulary.
        for noun, items in index.items():
            if len(items) != 1:
                continue
            for m in re.finditer(rf"((?:[\w'’-]+\s+){{1,4}}){re.escape(noun)}\b", sentence, re.IGNORECASE):
                preceding = m.group(1).split()
                # A sentence-initial capital is ordinary casing, not a brand.
                if m.start(1) == 0 and preceding:
                    preceding = preceding[1:]
                brand_tokens = [
                    t for t in preceding if re.fullmatch(r"[A-Z][a-zA-Z]+", t) and t.lower() not in _NOT_BRANDS
                ]
                if not brand_tokens:
                    continue
                vocab = _item_vocab(items[0])
                if not any(t.lower() in vocab for t in brand_tokens):
                    violations.append(
                        ClaimViolation(
                            "brand_unverified",
                            f"attributes brand '{' '.join(brand_tokens)}' to the {noun} — not in closet record",
                            sentence,
                        )
                    )

    if violations:
        logger.info(
            "reply_claims_ungrounded",
            count=len(violations),
            kinds=sorted({v.kind for v in violations}),
        )
    return violations


# ── Season check (outfit items, not prose) ────────────────────────────────────

_MONTH_SEASON = {
    12: "winter",
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "fall",
    10: "fall",
    11: "fall",
}
_SEASON_ALIASES = {"fall": {"fall", "autumn"}, "autumn": {"fall", "autumn"}}


def audit_outfit_seasons(
    outfits: list[dict[str, Any]],
    closet_map: dict[str, dict[str, Any]],
    current_month: int | None,
) -> list[ClaimViolation]:
    """Flag recommended items whose closet season list excludes the current season."""
    if not current_month:
        return []
    season = _MONTH_SEASON.get(current_month)
    if not season:
        return []
    acceptable = _SEASON_ALIASES.get(season, {season}) | {"all", "all-season", "any"}

    violations: list[ClaimViolation] = []
    for outfit in outfits or []:
        for it in outfit.get("items") or []:
            record = (closet_map or {}).get(str(it.get("id") or ""))
            if not record:
                continue
            item_seasons = {str(s).lower() for s in (record.get("season") or [])}
            if item_seasons and not (item_seasons & acceptable):
                violations.append(
                    ClaimViolation(
                        "season_mismatch",
                        f"'{record.get('name')}' is tagged {sorted(item_seasons)} but current season is {season}",
                    )
                )
    return violations


# ── Suggestion-entry audit (styling_suggestions / purchase_gaps) ──────────────

# Prose-bearing keys inside suggestion/gap entries.
_ENTRY_TEXT_KEYS = ("tip", "reason")


def audit_suggestion_entries(
    entries: list[Any] | None,
    closet_map: dict[str, dict[str, Any]],
    ctx: GroundingContext,
    *,
    valid_item_ids: set[str] | None = None,
) -> tuple[list[Any], list[ClaimViolation]]:
    """Audit list-field entries (styling_suggestions, purchase_gaps).

    Two checks per entry:
    - the same prose claim audit as ``reply`` over the entry's text fields;
    - a ``closet_item_id`` that isn't in ``valid_item_ids`` (the FULL closet,
      not the RAG subset) is an inventory hallucination in a side channel.

    Unlike reply prose (sentence-redacted), flagged entries are dropped whole —
    a one-line tip with its claim removed is noise, not advice.

    Returns ``(kept_entries, violations)``.
    """
    kept: list[Any] = []
    violations: list[ClaimViolation] = []
    for entry in entries or []:
        texts: list[str] = []
        if isinstance(entry, str):
            texts = [entry]
        elif isinstance(entry, dict):
            texts = [str(entry[k]) for k in _ENTRY_TEXT_KEYS if entry.get(k)]
            item_id = str(entry.get("closet_item_id") or "")
            if item_id and valid_item_ids is not None and item_id not in valid_item_ids:
                violations.append(
                    ClaimViolation(
                        "ownership_unverified",
                        f"suggestion references closet_item_id '{item_id}' not in closet — entry dropped",
                    )
                )
                continue

        entry_violations: list[ClaimViolation] = []
        for text in texts:
            entry_violations.extend(audit_reply_claims(text, closet_map, ctx))
        if entry_violations:
            violations.extend(entry_violations)
            continue
        kept.append(entry)
    return kept, violations


# ── Redaction ─────────────────────────────────────────────────────────────────

_REDACTION_NOTE = "(I've removed a couple of details I couldn't verify against your closet.)"


def redact_ungrounded_claims(reply: str | None, violations: list[ClaimViolation]) -> tuple[str, int]:
    """Remove sentences carrying ungrounded claims. Returns (cleaned_reply, removed_count).

    Only sentence-level violations are redactable (season violations carry no
    sentence). If everything gets removed, a short note keeps the reply usable.
    """
    text = str(reply or "")
    bad = {v.sentence for v in violations if v.sentence}
    if not text.strip() or not bad:
        return text, 0

    kept = [s for s in _SENTENCE_SPLIT.split(text) if s not in bad]
    removed = len(_SENTENCE_SPLIT.split(text)) - len(kept)
    cleaned = " ".join(kept).strip()
    if removed and not cleaned:
        cleaned = _REDACTION_NOTE
    elif removed:
        cleaned = f"{cleaned} {_REDACTION_NOTE}"
    return cleaned, removed
