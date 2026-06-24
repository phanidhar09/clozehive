#!/usr/bin/env bash
# Self-fixing test loop runner.
# Mirrors the checks that GitHub Actions (.github/workflows/ci.yml) enforces, so
# that local green predicts CI green. Runs against each service's own .venv and
# exits 0 only when everything passes.
#
# Usage:
#   scripts/run-tests.sh              # lint + both test suites (CI order)
#   scripts/run-tests.sh lint         # backend-lint only (ruff/format/mypy/drift)
#   scripts/run-tests.sh gateway      # api-gateway pytest only
#   scripts/run-tests.sh agent        # ai-agent pytest only
#   scripts/run-tests.sh tests        # both pytest suites, no lint
#
# Env:
#   LF=1   re-run only last-failed pytest tests first (fast inner loop)
#
# Note: lint mirrors CI's backend-lint job (ruff==0.15.16, mypy==2.1.0). If those
# tools are missing from the gateway venv the lint step tells you how to install
# them. CI also runs frontend, ai-worker, coverage gates and docker builds — those
# are NOT mirrored here (this runner is Python lint + tests only).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GW="$ROOT/services/api-gateway"
TARGET="${1:-all}"
PYTEST_EXTRA="${PYTEST_EXTRA:-}"
# LF=1 reruns only last-failed tests first (fast inner loop); default: full suite.
[ "${LF:-0}" = "1" ] && PYTEST_EXTRA="--lf $PYTEST_EXTRA"

fail=0

run_lint() {
  local py="$GW/.venv/bin/python"
  if [ ! -x "$py" ]; then
    echo "✗ [lint] no gateway venv at $py — skipping"
    return 1
  fi
  if ! "$py" -m ruff --version >/dev/null 2>&1; then
    echo "✗ [lint] ruff/mypy not installed in gateway venv. Install the CI-pinned versions:"
    echo "    $py -m pip install 'ruff==0.15.16' 'mypy==2.1.0'"
    return 1
  fi
  local rc=0
  echo "── [lint] ruff check (app) ─────────────────────────────────"
  ( cd "$GW" && "$py" -m ruff check app ) || rc=1
  echo "── [lint] ruff format --check (app) ────────────────────────"
  ( cd "$GW" && "$py" -m ruff format --check app ) || rc=1
  echo "── [lint] mypy (app) ───────────────────────────────────────"
  ( cd "$GW" && "$py" -m mypy app --ignore-missing-imports ) || rc=1
  echo "── [lint] service drift ────────────────────────────────────"
  ( cd "$ROOT" && "$py" scripts/check_service_drift.py ) || rc=1
  if [ $rc -eq 0 ]; then echo "✓ [lint] clean"; else echo "✗ [lint] FAILED"; fi
  return $rc
}

run_suite() {
  local name="$1" dir="$2"
  local py="$dir/.venv/bin/python"
  if [ ! -x "$py" ]; then
    echo "✗ [$name] no venv at $py — skipping (run: python3 -m venv .venv && pip install -r requirements-dev.txt)"
    return 1
  fi
  echo "── [$name] pytest ──────────────────────────────────────────"
  ( cd "$dir" && "$py" -m pytest -q --tb=short --no-header $PYTEST_EXTRA )
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "✗ [$name] FAILED (exit $rc)"
    return 1
  fi
  echo "✓ [$name] green"
  return 0
}

case "$TARGET" in
  lint)    run_lint || fail=1 ;;
  gateway) run_suite api-gateway "$GW" || fail=1 ;;
  agent)   run_suite ai-agent   "$ROOT/services/ai-agent" || fail=1 ;;
  tests)
    run_suite api-gateway "$GW" || fail=1
    run_suite ai-agent   "$ROOT/services/ai-agent" || fail=1
    ;;
  all)
    run_lint || fail=1
    run_suite api-gateway "$GW" || fail=1
    run_suite ai-agent   "$ROOT/services/ai-agent" || fail=1
    ;;
  *) echo "usage: $0 [all|lint|tests|gateway|agent]"; exit 2 ;;
esac

if [ $fail -eq 0 ]; then
  echo "ALL GREEN ✓"
else
  echo "SUITES FAILED ✗"
fi
exit $fail
