"""Scorers for the eval harness.

Pure functions over pipeline outputs — no I/O, no LLM calls — so each suite is
hermetic, fast, and safe to run in CI. Kept separate from the runner so scorers
can be unit-tested and reused.

Two suites today:

- **routing** — scores ``model_router.route`` against an expected capability
  tier. Lets you sweep ``_ESCALATE_THRESHOLD`` and see accuracy move.
- **grounding** — scores ``validate_chat_response`` + ``score_response_quality``
  over a known model output + closet, asserting the harness removes hallucinated
  items and falls back when nothing usable remains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.api.v1.intelligence.services.model_router import RouteSignals, Tier, route
from app.core.ai_output_validator import score_response_quality, validate_chat_response


@dataclass
class CaseResult:
    """Outcome of scoring a single labeled case."""

    case_id: str
    suite: str
    passed: bool
    detail: str = ""
    metrics: dict[str, float] = field(default_factory=dict)


# ── Routing suite ─────────────────────────────────────────────────────────────


def score_routing_case(case: dict[str, Any]) -> CaseResult:
    """Run the deterministic router and compare its tier to the expected tier."""
    expected = str(case["expected_tier"]).lower()
    signals = RouteSignals(
        message=case.get("message", ""),
        has_images=bool(case.get("has_images", False)),
        closet_item_count=int(case.get("closet_item_count", 0)),
        expects_outfits=bool(case.get("expects_outfits", False)),
        weather_required=bool(case.get("weather_required", False)),
        history_depth=int(case.get("history_depth", 0)),
        constraint_count=int(case.get("constraint_count", 0)),
    )
    decision = route(signals)
    predicted = decision.tier.value
    passed = predicted == expected
    return CaseResult(
        case_id=str(case.get("id", "?")),
        suite="routing",
        passed=passed,
        detail=("" if passed else f"expected {expected}, got {predicted} (score={decision.score})"),
        metrics={"score": decision.score, "correct": float(passed)},
    )


# ── Grounding suite ───────────────────────────────────────────────────────────


def score_grounding_case(case: dict[str, Any]) -> CaseResult:
    """Validate a known model output against a closet and check grounding expectations."""
    valid_ids = {str(x) for x in case.get("valid_item_ids", [])}
    model_output = case.get("model_output")
    expect = case.get("expect") or {}

    # Copy dicts (the validator mutates in place); pass non-dicts through so the
    # "not a JSON object" hard-error path can be exercised too.
    data = dict(model_output) if isinstance(model_output, dict) else model_output
    validation = validate_chat_response(data, valid_ids)
    quality = score_response_quality(validation, len(valid_ids))

    # `should_fallback` mirrors the non-streaming/streaming hard-error gate:
    # structural errors AND no usable reply left.
    did_fallback = bool(validation.errors) and not validation.cleaned.get("reply")
    outfits = validation.cleaned.get("recommended_outfits") or []

    failures: list[str] = []
    if "should_fallback" in expect and did_fallback != bool(expect["should_fallback"]):
        failures.append(f"should_fallback={expect['should_fallback']} but did_fallback={did_fallback}")
    if "min_outfits" in expect and len(outfits) < int(expect["min_outfits"]):
        failures.append(f"outfits {len(outfits)} < min {expect['min_outfits']}")
    if "max_outfits" in expect and len(outfits) > int(expect["max_outfits"]):
        failures.append(f"outfits {len(outfits)} > max {expect['max_outfits']}")
    if (
        "max_hallucination_risk" in expect
        and quality.hallucination_risk > float(expect["max_hallucination_risk"]) + 1e-9
    ):
        failures.append(f"hallucination_risk {quality.hallucination_risk} > max {expect['max_hallucination_risk']}")
    if "items_removed" in expect and validation.items_removed != int(expect["items_removed"]):
        failures.append(f"items_removed {validation.items_removed} != {expect['items_removed']}")

    return CaseResult(
        case_id=str(case.get("id", "?")),
        suite="grounding",
        passed=not failures,
        detail="; ".join(failures),
        metrics={
            "hallucination_risk": quality.hallucination_risk,
            "quality_overall": quality.overall,
            "outfits": float(len(outfits)),
            "items_removed": float(validation.items_removed),
        },
    )


# Registry so the runner can dispatch by dataset name.
SUITES = {
    "routing": score_routing_case,
    "grounding": score_grounding_case,
}


def tier_names() -> set[str]:
    """Valid tier labels — used by the runner to validate datasets early."""
    return {t.value for t in Tier}
