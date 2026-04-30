#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
from pathlib import Path
import os
import shutil

root = Path(os.environ["ROOT_DIR"])
removed: list[Path] = []

named_dirs = {".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__"}
explicit_dirs = [root / "frontend" / "dist", root / "htmlcov", root / "coverage"]
explicit_files = [root / ".coverage", root / "coverage.xml", root / ".dmypy.json"]

for path in explicit_dirs:
    if path.is_dir():
        shutil.rmtree(path)
        removed.append(path.relative_to(root))

for path in root.rglob("*"):
    if path.is_dir() and path.name in named_dirs:
        shutil.rmtree(path)
        removed.append(path.relative_to(root))

for pattern in ("*.pyc", "*.pyo", "*.tsbuildinfo", "*.log", "*.tmp", "*.temp"):
    for path in root.rglob(pattern):
        if path.is_file():
            path.unlink()
            removed.append(path.relative_to(root))

for path in explicit_files:
    if path.is_file():
        path.unlink()
        removed.append(path.relative_to(root))

if removed:
    print("Removed generated artifacts:")
    for rel in sorted(removed):
        print(f"  {rel}")
else:
    print("No generated artifacts found.")
PY
