"""Deprecated ``build_chat_completion_client`` hook (always None)."""

from __future__ import annotations

import pytest

from vai_agent.config.settings import LlmProvider, Settings
from vai_agent.llm import build_chat_completion_client


def test_build_chat_completion_returns_none_when_provider_none() -> None:
    settings = Settings(
        model_provider=LlmProvider.none,
        _env_file=None,  # type: ignore[call-arg]
    )
    assert build_chat_completion_client(settings) is None


def test_build_chat_completion_returns_none_when_openai_compatible_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP OpenAI-compatible client was removed; hook stays for imports."""

    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_KEY", "secret")
    monkeypatch.setenv("MODEL_NAME", "vendor/model-name")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert build_chat_completion_client(settings) is None


def test_build_chat_completion_returns_none_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_NAME", "x")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert build_chat_completion_client(settings) is None


def test_deprecated_openrouter_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When only OPENROUTER_* is set, settings still resolve."""

    for key in (
        "MODEL_API_KEY",
        "MODEL_NAME",
        "MODEL_BASE_URL",
        "MODEL_PROVIDER",
        "LLM_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "legacy/model")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://example.local/v1")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.model_provider is LlmProvider.openai_compatible
    assert settings.effective_model_api_key is not None
    assert settings.effective_model_api_key.get_secret_value() == "legacy-key"
    assert settings.effective_model_name == "legacy/model"
    assert settings.effective_model_base_url == "https://example.local/v1"


def test_model_env_wins_over_openrouter_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both MODEL_* and OPENROUTER_* are set, MODEL_* takes precedence."""

    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_KEY", "primary-key")
    monkeypatch.setenv("MODEL_NAME", "primary/model")
    monkeypatch.setenv("MODEL_BASE_URL", "https://primary.local/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "legacy/model")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://legacy.local/v1")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.effective_model_api_key is not None
    assert settings.effective_model_api_key.get_secret_value() == "primary-key"
    assert settings.effective_model_name == "primary/model"
    assert settings.effective_model_base_url == "https://primary.local/v1"


def test_llm_provider_kwarg_alias() -> None:
    settings = Settings(
        llm_provider=LlmProvider.none,
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.model_provider is LlmProvider.none
    assert settings.llm_provider is LlmProvider.none
