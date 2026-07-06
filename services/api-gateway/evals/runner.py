"""Eval harness runner.

Loads the golden datasets under ``evals/datasets/``, scores each case, prints a
per-suite report, and exits non-zero if any suite falls below its pass-rate gate
(so it can double as a regression check in CI).

Usage (from ``services/api-gateway``)::

    python -m evals.runner                     # run all suites, human report
    python -m evals.runner --suite routing     # one suite
    python -m evals.runner --json out.json      # also write machine-readable results
    python -m evals.runner --min-pass 0.9       # gate: fail if pass-rate < 0.9

The suites are fully deterministic (no network, no LLM, no DB), so a run costs
nothing and is safe to invoke on every change while tuning thresholds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from evals.scorers import SUITES, CaseResult, tier_names

DATASETS_DIR = Path(__file__).parent / "datasets"


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text()) or {}
    cases = data.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError(f"{path.name}: 'cases' must be a list")
    return cases


def _validate_routing_dataset(cases: list[dict[str, Any]]) -> None:
    valid = tier_names()
    for case in cases:
        tier = str(case.get("expected_tier", "")).lower()
        if tier not in valid:
            raise ValueError(f"routing case {case.get('id')}: expected_tier '{tier}' not in {sorted(valid)}")


def run_suite(name: str) -> list[CaseResult]:
    scorer = SUITES[name]
    path = DATASETS_DIR / f"{name}.yaml"
    if not path.exists():
        return []
    cases = _load_dataset(path)
    if name == "routing":
        _validate_routing_dataset(cases)
    return [scorer(case) for case in cases]


def _print_report(results: list[CaseResult]) -> None:
    by_suite: dict[str, list[CaseResult]] = {}
    for r in results:
        by_suite.setdefault(r.suite, []).append(r)

    for suite, items in sorted(by_suite.items()):
        passed = sum(1 for i in items if i.passed)
        total = len(items)
        rate = passed / total if total else 0.0
        print(f"\n── {suite}: {passed}/{total} passed ({rate:.0%}) ──")
        for i in items:
            mark = "✓" if i.passed else "✗"
            line = f"  {mark} {i.case_id}"
            if not i.passed and i.detail:
                line += f"  — {i.detail}"
            print(line)


def _suite_pass_rate(results: list[CaseResult], suite: str) -> float:
    items = [r for r in results if r.suite == suite]
    return (sum(1 for i in items if i.passed) / len(items)) if items else 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ClozeHive offline eval harness.")
    parser.add_argument("--suite", choices=sorted(SUITES), help="Run a single suite (default: all).")
    parser.add_argument("--json", dest="json_out", help="Write machine-readable results to this path.")
    parser.add_argument(
        "--min-pass",
        type=float,
        default=0.0,
        help="Fail (exit 1) if any suite's pass-rate is below this fraction. Default 0.0 (report only).",
    )
    args = parser.parse_args(argv)

    suites = [args.suite] if args.suite else list(SUITES)
    results: list[CaseResult] = []
    for name in suites:
        results.extend(run_suite(name))

    _print_report(results)

    if args.json_out:
        payload = [
            {"case_id": r.case_id, "suite": r.suite, "passed": r.passed, "detail": r.detail, "metrics": r.metrics}
            for r in results
        ]
        Path(args.json_out).write_text(json.dumps(payload, indent=2))
        print(f"\nWrote {len(payload)} results to {args.json_out}")

    failed_gate = [s for s in suites if _suite_pass_rate(results, s) < args.min_pass]
    if failed_gate:
        print(f"\nGATE FAILED (min-pass={args.min_pass:.0%}): {', '.join(failed_gate)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
