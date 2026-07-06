"""Regression guard for the offline eval harness.

The eval suites are deterministic (no network/LLM/DB), so we run them in CI. A
drop below the pass-rate floor means a routing-threshold or grounding-logic
change regressed against the golden set — intentional changes should update the
dataset in the same PR.
"""

from __future__ import annotations

from evals.runner import run_suite

# Floors, not exact matches, so the router threshold has a little tuning headroom
# before CI fails. Tighten if the golden set grows and stabilises.
_ROUTING_FLOOR = 0.9
_GROUNDING_FLOOR = 1.0


def _pass_rate(results) -> float:
    return sum(1 for r in results if r.passed) / len(results) if results else 0.0


def test_routing_suite_meets_floor():
    results = run_suite("routing")
    assert len(results) >= 12, "routing golden set unexpectedly small"
    rate = _pass_rate(results)
    failures = [f"{r.case_id}: {r.detail}" for r in results if not r.passed]
    assert rate >= _ROUTING_FLOOR, f"routing accuracy {rate:.0%} < {_ROUTING_FLOOR:.0%}: {failures}"


def test_grounding_suite_all_pass():
    results = run_suite("grounding")
    assert len(results) >= 6, "grounding golden set unexpectedly small"
    rate = _pass_rate(results)
    failures = [f"{r.case_id}: {r.detail}" for r in results if not r.passed]
    assert rate >= _GROUNDING_FLOOR, f"grounding pass-rate {rate:.0%} < {_GROUNDING_FLOOR:.0%}: {failures}"
