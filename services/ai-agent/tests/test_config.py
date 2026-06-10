"""Settings validation — no network, no OpenAI."""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings, _sanitize_openai_api_base


class TestHasValidOpenAIKey:
    def test_placeholder_key_is_invalid(self) -> None:
        s = Settings(openai_api_key="sk-your-openai-key")
        assert s.has_valid_openai_key is False

    def test_empty_key_is_invalid(self) -> None:
        assert Settings(openai_api_key="").has_valid_openai_key is False

    def test_reserved_test_key_is_invalid(self) -> None:
        assert Settings(openai_api_key="sk-test").has_valid_openai_key is False

    def test_real_looking_key_is_valid(self) -> None:
        assert Settings(openai_api_key="sk-alive-and-well").has_valid_openai_key is True

    def test_non_sk_prefix_is_invalid(self) -> None:
        assert Settings(openai_api_key="pk-something").has_valid_openai_key is False


class TestSanitizeOpenAIBaseURL:
    def test_official_url_unchanged(self) -> None:
        assert _sanitize_openai_api_base("https://api.openai.com/v1") == "https://api.openai.com/v1"

    def test_localhost_4000_reset_to_official(self) -> None:
        result = _sanitize_openai_api_base("http://localhost:4000/v1")
        assert result == "https://api.openai.com/v1"

    def test_empty_url_defaults_to_official(self) -> None:
        assert _sanitize_openai_api_base("") == "https://api.openai.com/v1"

    def test_custom_proxy_url_preserved(self) -> None:
        url = "https://my-proxy.example.com/v1"
        assert _sanitize_openai_api_base(url) == url


class TestSettingsDefaults:
    def test_default_environment_is_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert Settings().environment == "development"

    def test_is_production_false_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert Settings().is_production is False

    def test_is_production_true_when_set(self) -> None:
        assert Settings(environment="production").is_production is True

    def test_origins_list_parsed_from_comma_string(self) -> None:
        s = Settings(allowed_origins="http://a.com,http://b.com")
        assert s.origins_list == ["http://a.com", "http://b.com"]

    def test_origins_list_strips_whitespace(self) -> None:
        s = Settings(allowed_origins="http://a.com , http://b.com ")
        assert all(" " not in o for o in s.origins_list)


class TestGetSettingsCaching:
    def test_returns_same_instance_when_called_twice(self) -> None:
        get_settings.cache_clear()
        a = get_settings()
        b = get_settings()
        assert a is b
        get_settings.cache_clear()
