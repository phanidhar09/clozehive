"""Settings and MCP flag behaviour (no network, no OpenAI)."""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


def test_enable_mcp_tools_default_false() -> None:
    s = Settings()
    assert s.enable_mcp_tools is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("", False),
        (False, False),
        (True, True),
    ],
)
def test_enable_mcp_tools_parsing(raw: str | bool, expected: bool) -> None:
    s = Settings(enable_mcp_tools=raw)  # type: ignore[arg-type]
    assert s.enable_mcp_tools is expected


def test_mcp_endpoints_for_logging_shape() -> None:
    s = Settings(
        mcp_weather_url="http://mcp-weather:8010/sse",
        mcp_vision_url="http://vision.example:8011/custom/sse",
    )
    rows = s.mcp_endpoints_for_logging()
    by_name = {r["name"]: r for r in rows}
    assert by_name["weather"]["host"] == "mcp-weather:8010"
    assert by_name["weather"]["path"] == "/sse"
    assert by_name["vision"]["host"] == "vision.example:8011"
    assert by_name["vision"]["path"] == "/custom/sse"


def test_get_settings_cached_instance() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
