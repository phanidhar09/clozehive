"""Unit tests for app.utils.username — pure functions only (no DB)."""
import pytest

from app.utils.username import normalize_username


@pytest.mark.parametrize(
    "input_value, expected",
    [
        ("Alice Johnson", "alice_johnson"),
        ("  Bob  ", "bob"),
        ("María García", "mara_garca"),          # non-ASCII stripped
        ("user!@#name", "username"),              # special chars stripped
        ("__leading__trailing__", "leading_trailing"),  # double underscores collapsed
        ("a" * 40, "a" * 30),                     # truncated to 30
        ("", "user"),                              # fallback
        ("!@#$%", "user"),                         # all stripped → fallback
        ("John_Doe_123", "john_doe_123"),
        ("UPPER CASE", "upper_case"),
    ],
)
def test_normalize_username(input_value: str, expected: str) -> None:
    assert normalize_username(input_value) == expected
