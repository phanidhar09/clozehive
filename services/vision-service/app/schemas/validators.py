"""Reusable schema validators."""

from __future__ import annotations


def strip_string(v: str) -> str:
    return v.strip() if v else v
