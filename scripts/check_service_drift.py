#!/usr/bin/env python3
"""Fail CI when shared-source files drift between services.

Some modules are deliberately identical across services (we don't have a
shared pip package because each service builds from its own Docker context).
This check keeps those copies byte-identical: edit one copy, copy it to its
twin, commit both.

Usage:  python scripts/check_service_drift.py
Exit 0 when all pairs match, 1 when any pair differs.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Pairs that must stay byte-identical. Add a pair here whenever a module is
# unified across services. (Empty since the standalone vision-service was
# retired — the api-gateway now owns the only copy of the vision pipeline,
# fashion-analysis, and gemini modules.)
SHARED_PAIRS: list[tuple[str, str]] = []


def main() -> int:
    failures: list[tuple[str, str]] = []
    for left, right in SHARED_PAIRS:
        left_path = REPO_ROOT / left
        right_path = REPO_ROOT / right
        for p in (left_path, right_path):
            if not p.is_file():
                print(f"DRIFT CHECK ERROR: missing file {p.relative_to(REPO_ROOT)}")
                failures.append((left, right))
                break
        else:
            if left_path.read_bytes() != right_path.read_bytes():
                failures.append((left, right))

    if failures:
        print("Shared service files have drifted:\n")
        for left, right in failures:
            print(f"  {left}\n  {right}\n")
            print(f"  Fix: review `diff {left} {right}`, merge intentionally, then")
            print("  copy the merged file over both paths so they are byte-identical.\n")
        return 1

    print(f"OK: {len(SHARED_PAIRS)} shared file pair(s) in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
