"""Startup wiring tests for :mod:`vai_agent.bootstrap`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

import vai_agent.bootstrap as bootstrap
from vai_agent.config.settings import LlmProvider, Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader


@pytest.fixture()
def sample_profile():
    return ProfileLoader(Path(__file__).parent / "fixtures" / "profiles").load("sample")


def test_create_app_sets_runtime_state_when_startup_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_profile,
) -> None:
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(Path(__file__).parent / "fixtures" / "profiles"),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst",
        llm_provider=LlmProvider.none,
        chroma_persist_dir=str(tmp_path / "chroma"),
        _env_file=None,
    )

    monkeypatch.setattr(
        bootstrap,
        "get_connection_settings",
        lambda: ConnectionSettings(
            _env_file=None,
            host="127.0.0.1",
            port=1433,
            database="db",
            username="u",
            password=SecretStr("pw"),
        ),
    )

    app = bootstrap.create_app(settings)
    assert getattr(app.state, "llm_service", None) is None
    assert app.state.profile.meta.profile_id == "sample"
    assert app.state.agent is not None
    assert app.state.memory is not None
    assert app.state.readiness["ready"] is True


def test_create_app_marks_degraded_when_profile_missing() -> None:
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="missing",
        profiles_root=str(Path(__file__).parent / "fixtures" / "profiles"),
        llm_provider=LlmProvider.none,
        _env_file=None,
    )
    app = bootstrap.create_app(settings)
    assert app.state.agent is None
    assert app.state.readiness["ready"] is False
    assert app.state.readiness["profile_ready"] is False
