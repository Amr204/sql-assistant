"""Tests for :func:`build_vanna_llm_service` (Vanna LlmService factory)."""

from __future__ import annotations

import pytest
from vanna.integrations.mock import MockLlmService
from vanna.integrations.openai import OpenAILlmService

from vai_agent.config.settings import LlmProvider, Settings
from vai_agent.llm.retry_llm import RetryLlmService
from vai_agent.vanna_integration.model_llm import build_vanna_llm_service


def test_build_vanna_llm_returns_mock_when_provider_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    svc = build_vanna_llm_service(settings)
    assert isinstance(svc, MockLlmService)


def test_build_vanna_llm_returns_mock_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_NAME", "vendor/model-name")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    svc = build_vanna_llm_service(settings)
    assert isinstance(svc, MockLlmService)


def test_build_vanna_llm_returns_mock_without_model_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_KEY", "secret")
    monkeypatch.setenv("MODEL_NAME", "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    svc = build_vanna_llm_service(settings)
    assert isinstance(svc, MockLlmService)


def test_build_vanna_llm_wraps_openai_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_NAME", "vendor/model-name")
    monkeypatch.setenv("MODEL_BASE_URL", "https://example.local/v1")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    svc = build_vanna_llm_service(settings)
    assert isinstance(svc, RetryLlmService)
    assert isinstance(svc._inner, OpenAILlmService)
    assert svc._fallback is None


def test_build_vanna_llm_configures_fallback_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_NAME", "primary/model")
    monkeypatch.setenv("MODEL_FALLBACK_NAME", "fallback/model")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    svc = build_vanna_llm_service(settings)
    assert isinstance(svc, RetryLlmService)
    assert isinstance(svc._fallback, OpenAILlmService)


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


def test_llm_provider_kwarg_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "none")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.model_provider is LlmProvider.none
    assert settings.llm_provider is LlmProvider.none
