"""Tests for :mod:`vai_agent.config.settings`."""

from __future__ import annotations

import pytest

from vai_agent.config.settings import AppEnv, Settings, get_settings


def test_defaults_load_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must load with sane defaults when no env vars are set."""

    for key in ("APP_ENV", "APP_HOST", "APP_PORT", "LOG_LEVEL", "LOG_FORMAT"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env is AppEnv.dev
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"
    assert settings.is_dev is True
    assert settings.is_prod is False


def test_env_overrides_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables must override defaults (case-insensitive)."""

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("APP_PORT", "9001")
    monkeypatch.setenv("LOG_FORMAT", "json")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env is AppEnv.prod
    assert settings.app_port == 9001
    assert settings.log_format == "json"
    assert settings.is_prod is True
    assert settings.is_dev is False


def test_invalid_port_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ports outside 1..65535 must raise a validation error."""

    monkeypatch.setenv("APP_PORT", "70000")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_get_settings_is_cached() -> None:
    """``get_settings`` must return the same instance across calls."""

    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()
