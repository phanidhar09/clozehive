"""Vision golden set — extraction-quality scoring for the garment vision pipeline.

Unlike the deterministic hallucination/routing suites, judging vision
*extraction quality* requires the model. Three modes:

- ``--live``      call the vision function on each golden image and score the
                  extracted fields against labels (needs OPENAI_API_KEY; costs
                  a few cents per run).
- ``--record``    live run that also snapshots each response to
                  ``datasets/vision/recordings/<fn>/<id>.json``.
- *(default)*     offline: score the saved recordings — no network, safe for
                  CI. Catches label drift and scoring regressions; refresh the
                  recordings whenever the prompt or model changes.

This is the measurement gate for vision model/prompt changes: run ``--live``
before and after a change (e.g. flagship → mini via the ``vision_*`` tiering
config) and compare per-field accuracy instead of guessing.

Usage (from services/api-gateway)::

    python -m evals.vision_golden                    # score recordings
    python -m evals.vision_golden --live             # call the model now
    python -m evals.vision_golden --record           # live + save recordings
    python -m evals.vision_golden --fn analyze_image # score the mini-model tier
    python -m evals.vision_golden --live --min-accuracy 0.8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml

VISION_DIR = Path(__file__).parent / "datasets" / "vision"
IMAGES_DIR = VISION_DIR / "images"
RECORDINGS_DIR = VISION_DIR / "recordings"

# Fields scored per case. fit/material are skipped when the label is null
# (synthetic starter images can't ground them).
SCORED_FIELDS = ("category", "color", "pattern", "fit", "material")


def load_cases() -> list[dict[str, Any]]:
    data = yaml.safe_load((VISION_DIR / "labels.yaml").read_text()) or {}
    cases = data.get("cases") or []
    if not isinstance(cases, list) or not cases:
        raise ValueError("labels.yaml: 'cases' must be a non-empty list")
    return cases


# ── Field extraction (both response shapes) ───────────────────────────────────


def extract_fields(response: dict[str, Any]) -> dict[str, str]:
    """Normalise either vision response shape (bulk dict or legacy upload dict)
    into the scored field set, lowercased."""

    def _s(*keys: str) -> str:
        for k in keys:
            v = response.get(k)
            if v and str(v).strip().lower() not in ("unknown", "none", "null"):
                return str(v).strip().lower()
        return ""

    return {
        "category": _s("category"),
        "color": _s("primary_color", "color"),
        "pattern": _s("pattern"),
        "fit": _s("fit"),
        "material": _s("material", "fabric"),
    }


# ── Scoring ────────────────────────────────────────────────────────────────────


def score_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Score one case. Returns per-field verdicts: True/False, or None = not scored."""
    expect = case.get("expect") or {}
    got = extract_fields(response)
    verdicts: dict[str, bool | None] = {}

    verdicts["category"] = got["category"] == str(expect.get("category", "")).lower()

    color_any = [str(c).lower() for c in (expect.get("color_any") or [])]
    verdicts["color"] = any(c in got["color"] for c in color_any) if color_any else None

    pattern_any = [str(p).lower() for p in (expect.get("pattern_any") or [])]
    verdicts["pattern"] = any(p in got["pattern"] for p in pattern_any) if pattern_any else None

    for field in ("fit", "material"):
        expected = expect.get(field)
        verdicts[field] = (str(expected).lower() in got[field]) if expected else None

    scored = {k: v for k, v in verdicts.items() if v is not None}
    return {
        "id": case["id"],
        "verdicts": verdicts,
        "got": got,
        "passed": sum(1 for v in scored.values() if v),
        "scored": len(scored),
    }


# ── Response acquisition ───────────────────────────────────────────────────────


async def _call_model(case: dict[str, Any], fn: str) -> dict[str, Any]:
    from app.api.v1.wardrobe.services import vision_service
    from app.core.analytics import LLMTelemetry

    image_bytes = (IMAGES_DIR / case["image"]).read_bytes()
    telemetry = LLMTelemetry(operation="vision_golden_eval")
    if fn == "analyze_image":
        return await vision_service.analyze_image(image_bytes, "image/png", telemetry=telemetry)
    return await vision_service.analyze_for_bulk(image_bytes, "image/png", telemetry=telemetry)


def _recording_path(case_id: str, fn: str) -> Path:
    return RECORDINGS_DIR / fn / f"{case_id}.json"


async def get_responses(
    cases: list[dict[str, Any]], *, live: bool, record: bool, fn: str
) -> dict[str, dict[str, Any] | None]:
    responses: dict[str, dict[str, Any] | None] = {}
    for case in cases:
        if live or record:
            resp = await _call_model(case, fn)
            responses[case["id"]] = resp
            if record:
                path = _recording_path(case["id"], fn)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(resp, indent=2, default=str))
        else:
            path = _recording_path(case["id"], fn)
            responses[case["id"]] = json.loads(path.read_text()) if path.exists() else None
    return responses


# ── Report ─────────────────────────────────────────────────────────────────────


def _print_report(results: list[dict[str, Any]], skipped: list[str], fn: str, mode: str) -> float:
    print(f"\nVision golden set — fn={fn}, mode={mode}")
    print("=" * 72)
    print(f"{'Case':<24}" + "".join(f"{f:>10}" for f in SCORED_FIELDS))
    print("-" * 72)
    field_pass: dict[str, int] = dict.fromkeys(SCORED_FIELDS, 0)
    field_total: dict[str, int] = dict.fromkeys(SCORED_FIELDS, 0)
    for r in results:
        cells = []
        for f in SCORED_FIELDS:
            v = r["verdicts"][f]
            if v is None:
                cells.append(f"{'—':>10}")
            else:
                field_total[f] += 1
                field_pass[f] += int(v)
                cells.append(f"{'✓' if v else '✗ ' + r['got'][f][:6]:>10}"[:10].rjust(10))
        print(f"{r['id']:<24}" + "".join(cells))
    print("-" * 72)
    acc_cells = []
    for f in SCORED_FIELDS:
        acc_cells.append(f"{(field_pass[f] / field_total[f] * 100):>9.0f}%" if field_total[f] else f"{'—':>10}")
    print(f"{'FIELD ACCURACY':<24}" + "".join(acc_cells))
    total_pass = sum(r["passed"] for r in results)
    total_scored = sum(r["scored"] for r in results)
    overall = total_pass / total_scored if total_scored else 0.0
    print(f"\nOVERALL: {total_pass}/{total_scored} scored fields correct ({overall:.1%})")
    if skipped:
        print(f"Skipped (no recording): {', '.join(skipped)} — run with --record to create them.")
    print("=" * 72)
    return overall


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score vision extraction against the golden set.")
    ap.add_argument("--live", action="store_true", help="Call the vision model (needs OPENAI_API_KEY).")
    ap.add_argument("--record", action="store_true", help="Live run + save responses as recordings.")
    ap.add_argument(
        "--fn",
        choices=("analyze_for_bulk", "analyze_image"),
        default="analyze_for_bulk",
        help="Which vision tier to score (analyze_for_bulk = flagship enrichment, analyze_image = mini categorization).",
    )
    ap.add_argument("--json", dest="json_out", help="Write machine-readable results to this path.")
    ap.add_argument(
        "--min-accuracy",
        type=float,
        default=0.0,
        help="Exit 1 if overall scored-field accuracy is below this fraction.",
    )
    args = ap.parse_args(argv)

    cases = load_cases()
    responses = asyncio.run(get_responses(cases, live=args.live, record=args.record, fn=args.fn))

    results: list[dict[str, Any]] = []
    skipped: list[str] = []
    for case in cases:
        resp = responses.get(case["id"])
        if resp is None:
            skipped.append(case["id"])
            continue
        results.append(score_case(case, resp))

    if not results:
        print("No recordings found and --live not set — nothing to score.")
        print("Run: python -m evals.vision_golden --record   (needs OPENAI_API_KEY)")
        return 0

    mode = "live" if (args.live or args.record) else "recorded"
    overall = _print_report(results, skipped, args.fn, mode)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"fn": args.fn, "mode": mode, "overall": round(overall, 4), "results": results}, indent=2)
        )
        print(f"Wrote results to {args.json_out}")

    if args.min_accuracy and overall < args.min_accuracy:
        print(f"\nGATE FAILED: overall accuracy {overall:.1%} < {args.min_accuracy:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
