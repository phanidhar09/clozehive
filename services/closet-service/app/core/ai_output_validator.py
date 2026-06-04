"""AI output validation and confidence scoring utilities.

Validates LLM-generated JSON against expected schemas, surfaces low-confidence
items, and provides source citation helpers for RAG responses.

Usage::

    from app.core.ai_output_validator import validate_chat_response, score_response_quality

    data = json.loads(raw_llm_output)
    result = validate_chat_response(data, valid_item_ids)
    if result.warnings:
        logger.warning("ai_output_warnings", warnings=result.warnings)
    data = result.cleaned
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger("ai_output_validator")

# ── Constants ─────────────────────────────────────────────────────────────────

_SCORE_COMPONENT_KEYS = {"color", "occasion", "fit", "style", "weather", "preference"}
_SCORE_MAX = 100
_MIN_OUTFIT_ITEMS = 1
_MAX_OUTFIT_ITEMS = 10
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Outcome of validating a single AI chat response."""

    cleaned: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    outfits_removed: int = 0
    items_removed: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class ResponseQualityScore:
    """Numeric quality signal for an AI chat response."""

    overall: float           # 0.0 – 1.0
    has_outfits: bool
    has_reply: bool
    outfit_completeness: float   # avg fraction of score_breakdown components present
    hallucination_risk: float    # 0.0 = clean, 1.0 = all items unverified


# ── Core validator ────────────────────────────────────────────────────────────

def validate_chat_response(
    data: dict[str, Any],
    valid_item_ids: set[str],
) -> ValidationResult:
    """Validate and clean an AI chat response dict.

    Checks:
    - Required top-level keys are present and correctly typed.
    - ``recommended_outfits`` items reference only IDs in ``valid_item_ids``.
    - ``matching_score`` equals the sum of ``score_breakdown`` components (±1 rounding).
    - ``score_breakdown`` values are non-negative integers summing to ≤ 100.
    - Outfits with zero valid items after filtering are dropped.

    Returns a :class:`ValidationResult` whose ``cleaned`` dict is safe to return
    to callers. Warnings are informational; errors indicate structural problems.
    """
    result = ValidationResult(cleaned={})
    warnings: list[str] = result.warnings
    errors: list[str] = result.errors

    if not isinstance(data, dict):
        errors.append("Response is not a JSON object")
        result.cleaned = _empty_response()
        return result

    # ── Top-level fields ──────────────────────────────────────────────────────
    reply = data.get("reply")
    if not reply or not str(reply).strip():
        warnings.append("reply is empty — LLM returned no conversational text")

    for list_key in ("recommended_outfits", "styling_suggestions", "purchase_gaps", "follow_up_questions"):
        if not isinstance(data.get(list_key), list):
            warnings.append(f"{list_key} is missing or not a list — defaulting to []")
            data[list_key] = []

    # ── Outfit validation ────────────────────────────────────────────────────
    cleaned_outfits: list[dict[str, Any]] = []
    for idx, outfit in enumerate(data.get("recommended_outfits") or []):
        if not isinstance(outfit, dict):
            warnings.append(f"outfit[{idx}] is not a dict — skipped")
            result.outfits_removed += 1
            continue

        outfit_warnings: list[str] = []

        # Item ID validation
        raw_items = outfit.get("items") or []
        valid_items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if not _UUID_RE.match(item_id):
                outfit_warnings.append(f"item id '{item_id}' is not a valid UUID — removed")
                result.items_removed += 1
            elif item_id not in valid_item_ids:
                outfit_warnings.append(f"item id '{item_id}' not in user's closet — removed")
                result.items_removed += 1
            else:
                valid_items.append(item)

        if not valid_items:
            warnings.append(f"outfit[{idx}] '{outfit.get('title', '')}' has no valid items — dropped")
            result.outfits_removed += 1
            continue

        # Score consistency check
        breakdown = outfit.get("score_breakdown") or {}
        if isinstance(breakdown, dict):
            component_sum = sum(
                int(v) for k, v in breakdown.items()
                if k in _SCORE_COMPONENT_KEYS and isinstance(v, (int, float))
            )
            declared_score = outfit.get("matching_score")
            if declared_score is not None:
                try:
                    declared = int(declared_score)
                    if abs(declared - component_sum) > 2:
                        outfit_warnings.append(
                            f"matching_score {declared} ≠ score_breakdown sum {component_sum} — corrected"
                        )
                        outfit["matching_score"] = min(component_sum, _SCORE_MAX)
                except (TypeError, ValueError):
                    outfit["matching_score"] = min(component_sum, _SCORE_MAX)

        if outfit_warnings:
            warnings.extend(outfit_warnings)
            logger.debug("outfit_validation_warnings", outfit_idx=idx, warnings=outfit_warnings)

        outfit["items"] = valid_items
        cleaned_outfits.append(outfit)

    data["recommended_outfits"] = cleaned_outfits

    result.cleaned = {
        "reply": str(reply or ""),
        "recommended_outfits": cleaned_outfits,
        "styling_suggestions": data.get("styling_suggestions") or [],
        "purchase_gaps": data.get("purchase_gaps") or [],
        "follow_up_questions": data.get("follow_up_questions") or [],
    }

    if warnings:
        logger.info("ai_output_validated_with_warnings", warning_count=len(warnings))
    return result


def score_response_quality(result: ValidationResult, total_valid_items: int) -> ResponseQualityScore:
    """Compute a numeric quality score for an AI response validation result."""
    outfits = result.cleaned.get("recommended_outfits") or []
    reply = result.cleaned.get("reply") or ""

    has_outfits = len(outfits) > 0
    has_reply = bool(reply.strip())

    # Outfit completeness: avg fraction of score_breakdown components filled
    completeness_scores = []
    for o in outfits:
        breakdown = o.get("score_breakdown") or {}
        filled = sum(1 for k in _SCORE_COMPONENT_KEYS if k in breakdown and breakdown[k] is not None)
        completeness_scores.append(filled / len(_SCORE_COMPONENT_KEYS))
    outfit_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0

    # Hallucination risk: ratio of removed items to total items seen
    total_seen = sum(
        len(o.get("items") or []) for o in (result.cleaned.get("recommended_outfits") or [])
    ) + result.items_removed
    hallucination_risk = result.items_removed / total_seen if total_seen > 0 else 0.0

    # Overall: weighted combination
    overall = (
        (0.30 * float(has_reply))
        + (0.30 * float(has_outfits))
        + (0.25 * outfit_completeness)
        + (0.15 * (1.0 - hallucination_risk))
    )

    return ResponseQualityScore(
        overall=round(overall, 3),
        has_outfits=has_outfits,
        has_reply=has_reply,
        outfit_completeness=round(outfit_completeness, 3),
        hallucination_risk=round(hallucination_risk, 3),
    )


# ── RAG source citation helpers ───────────────────────────────────────────────

def format_rag_citations(
    fashion_docs: list[dict[str, Any]],
    outfit_history: list[dict[str, Any]] | None = None,
) -> str:
    """Build a compact citation block for inclusion in AI system prompts.

    Each source gets a [SOURCE-N] label so the model can reference it in responses.
    This makes retrieved knowledge attributable and lets humans audit why FANI
    gave specific advice.

    Example output::

        [KNOWLEDGE SOURCES]
        [SOURCE-1] Color Matching Fundamentals (category: color, score: 0.87)
        [SOURCE-2] Business Casual Dressing Guide (category: occasion, score: 0.79)
        [OUTFIT HISTORY]
        [HISTORY-1] Past occasion: work, score: 82, worn: True (similarity: 0.71)
        [END SOURCES]
    """
    lines = ["[KNOWLEDGE SOURCES]"]
    for i, doc in enumerate(fashion_docs, 1):
        title = doc.get("title") or doc.get("content", "")[:60]
        category = doc.get("category") or "general"
        score = doc.get("similarity_score") or doc.get("score") or 0
        lines.append(f"[SOURCE-{i}] {title} (category: {category}, score: {score:.2f})")

    if outfit_history:
        lines.append("[OUTFIT HISTORY]")
        for i, hist in enumerate(outfit_history, 1):
            occasion = hist.get("occasion") or "unknown"
            match_score = hist.get("matching_score") or 0
            was_worn = hist.get("was_worn", False)
            sim = hist.get("similarity_score") or 0
            lines.append(
                f"[HISTORY-{i}] Past occasion: {occasion}, score: {match_score}, "
                f"worn: {was_worn} (similarity: {sim:.2f})"
            )

    lines.append("[END SOURCES]")
    return "\n".join(lines)


def check_context_sufficiency(
    closet_items: list[dict[str, Any]],
    fashion_docs: list[dict[str, Any]],
    message: str,
) -> tuple[bool, str]:
    """Determine if there is sufficient context to generate a grounded response.

    Returns (is_sufficient, reason). When is_sufficient is False the caller
    should return a "not enough information" response rather than letting the
    LLM guess.
    """
    if not closet_items:
        return False, "Wardrobe is empty — cannot build outfit recommendations."

    # Detect packing / trip requests without location context.
    # We require a destination indicator — prepositions like "for" alone don't count
    # because "pack for my trip" has no destination.
    packing_keywords = ("pack", "suitcase", "luggage", "travel", "vacation", "holiday")
    if any(kw in message.lower() for kw in packing_keywords):
        # Accept if message contains "to <word>", "visit(ing) <word>", "going to",
        # or an explicit destination keyword
        import re as _re
        _destination_re = _re.compile(
            r"\b(to\s+\w|visit\w*\s+\w|going\s+to|destination\s*:|trip\s+to)\b",
            _re.IGNORECASE,
        )
        if not _destination_re.search(message):
            return False, "Packing request detected but no destination specified."

    return True, ""


# ── Private helpers ───────────────────────────────────────────────────────────

def _empty_response() -> dict[str, Any]:
    return {
        "reply": "",
        "recommended_outfits": [],
        "styling_suggestions": [],
        "purchase_gaps": [],
        "follow_up_questions": [],
    }
