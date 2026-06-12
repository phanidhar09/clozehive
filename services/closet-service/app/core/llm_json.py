"""Shared parsing for LLM JSON responses.

Every service that asks a model for JSON needs the same two steps: strip
markdown code fences the model sometimes adds despite instructions, then
parse. Use these helpers instead of hand-rolling per service.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```")


def strip_code_fences(text: str) -> str:
    """Return the JSON payload with any surrounding ```json fences removed."""
    text = text.strip()
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text


def parse_llm_json(text: str) -> Any:
    """Parse an LLM response expected to be JSON, tolerating code fences.

    Raises json.JSONDecodeError like json.loads — callers decide the fallback.
    """
    return json.loads(strip_code_fences(text))
