"""Guard for the vision golden set — dataset integrity + scorer logic.

Hermetic: no network, no model calls. The live accuracy run is on-demand
(``python -m evals.vision_golden --live``); CI only guarantees the dataset is
well-formed and the scorer judges correctly, so a broken label or a scoring
regression can't silently corrupt the measurement the vision tiering
decisions depend on.
"""

from __future__ import annotations

from evals.vision_golden import IMAGES_DIR, SCORED_FIELDS, extract_fields, load_cases, score_case

CANONICAL_CATEGORIES = {"tops", "bottoms", "shoes", "outerwear", "dresses", "accessories", "other"}


# ── Dataset integrity ──────────────────────────────────────────────────────────


def test_dataset_well_formed() -> None:
    cases = load_cases()
    assert len(cases) >= 8
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for case in cases:
        expect = case.get("expect") or {}
        assert (IMAGES_DIR / case["image"]).exists(), f"{case['id']}: image missing"
        assert expect.get("category") in CANONICAL_CATEGORIES, f"{case['id']}: bad category"
        assert expect.get("color_any"), f"{case['id']}: color_any required"


# ── Scorer logic ───────────────────────────────────────────────────────────────

CASE = {
    "id": "t",
    "expect": {"category": "tops", "color_any": ["navy", "blue"], "pattern_any": ["solid"], "fit": None},
}


def test_correct_extraction_scores_full() -> None:
    r = score_case(CASE, {"category": "tops", "primary_color": "Navy Blue", "pattern": "Solid"})
    assert r["passed"] == r["scored"] == 3
    # Unlabeled fields are not scored, not failed.
    assert r["verdicts"]["fit"] is None and r["verdicts"]["material"] is None


def test_wrong_category_and_color_fail() -> None:
    r = score_case(CASE, {"category": "bottoms", "primary_color": "burgundy", "pattern": "solid"})
    assert r["verdicts"]["category"] is False
    assert r["verdicts"]["color"] is False
    assert r["verdicts"]["pattern"] is True


def test_color_any_token_matching() -> None:
    # "blue" token inside a longer shade name must match.
    r = score_case(CASE, {"category": "tops", "primary_color": "light blue", "pattern": "solid"})
    assert r["verdicts"]["color"] is True


def test_fit_scored_only_when_labeled() -> None:
    case = {"id": "t2", "expect": {"category": "tops", "color_any": ["red"], "fit": "slim"}}
    hit = score_case(case, {"category": "tops", "primary_color": "red", "fit": "Slim"})
    miss = score_case(case, {"category": "tops", "primary_color": "red", "fit": "Oversized"})
    assert hit["verdicts"]["fit"] is True
    assert miss["verdicts"]["fit"] is False


def test_extract_fields_handles_both_response_shapes() -> None:
    bulk = extract_fields({"primary_color": "Navy", "material": "Cotton", "category": "Tops"})
    legacy = extract_fields({"color": "navy", "fabric": "cotton", "category": "tops"})
    assert bulk["color"] == legacy["color"] == "navy"
    assert bulk["material"] == legacy["material"] == "cotton"
    # "Unknown" placeholders are treated as absent, not as a wrong answer.
    assert extract_fields({"pattern": "Unknown"})["pattern"] == ""
    assert set(bulk) == set(SCORED_FIELDS)
