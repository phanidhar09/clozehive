"""Unit tests for the shared LLM JSON parsing helpers."""

from __future__ import annotations

import json

import pytest

from app.core.llm_json import parse_llm_json, strip_code_fences


def test_strips_json_fence() -> None:
    assert parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_strips_bare_fence() -> None:
    assert parse_llm_json('```\n[1, 2]\n```') == [1, 2]


def test_plain_json() -> None:
    assert parse_llm_json('  {"a": 1} ') == {"a": 1}


def test_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("not json at all")


def test_strip_code_fences_no_fence_passthrough() -> None:
    assert strip_code_fences(' {"x": 1} ') == '{"x": 1}'
