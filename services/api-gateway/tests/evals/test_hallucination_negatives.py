"""Regression guard for the hallucination negative-test harness.

Locks every *guarded* containment mechanism at full strength so a change to the
validator / context guard / sanitiser / claim-grounding audit that silently
drops a guardrail fails CI. The two ``structural`` categories carrying semantic
truth probes (Occasion, Outfit Compatibility) are locked at their honest 50%
floor — raising them needs the online LLM-judge eval, not a code tweak here.
"""

from __future__ import annotations

from evals.hallucination_negatives import run

# Categories with a dedicated deterministic guard must stay at 100% containment.
GUARDED_FULL = {
    "Inventory Hallucination",
    "Attribute Hallucination",
    "Weather Recommendation Hallucination",
    "Missing Context Hallucination",
    "User Preference Hallucination",
    "Shopping Hallucination",
    "Retrieval Hallucination (RAG)",
    "Image Hallucination",
    "Duplicate Hallucination",
    "Packing Hallucination",
    "Seasonal Hallucination",
    "Memory Hallucination",
    "Color Hallucination",
    "Brand Hallucination",
    "Confidence Calibration",
    "Retrieval Grounding Verification",
    "Recommendation Justification",
}

# Semantic-truth categories: structural probes must hold their floor.
STRUCTURAL_FLOOR = {
    "Occasion Hallucination": 0.5,
    "Outfit Compatibility Hallucination": 0.5,
}


def test_guarded_categories_fully_contained() -> None:
    rows = {r["category"]: r for r in run()}
    for name in GUARDED_FULL:
        row = rows[name]
        assert row["score"] == 1.0, f"{name} regressed to {row['score']}: {row['probes']}"


def test_structural_categories_hold_floor() -> None:
    rows = {r["category"]: r for r in run()}
    for name, floor in STRUCTURAL_FLOOR.items():
        row = rows[name]
        assert row["score"] >= floor, f"{name} fell below {floor}: {row['probes']}"


def test_end_to_end_score_reported() -> None:
    rows = run()
    total = sum(r["total"] for r in rows)
    passed = sum(r["passed"] for r in rows)
    assert total > 0
    # Floor set just under the current 95.1% — a dropped guard fails here too.
    assert passed / total >= 0.9
