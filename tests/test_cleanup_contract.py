"""Delivery / source-tree hygiene contracts (no accidental secrets or manual /chat orchestration)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_excludes_runtime_and_secrets() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert ".data/" in text
    assert ".pytest_cache/" in text
    assert ".ruff_cache/" in text
    assert "__pycache__/" in text or "__pycache__" in text
    assert "query_results_*.csv" in text


def test_no_manual_orchestration_in_chat_source() -> None:
    chat_file = REPO_ROOT / "src" / "vai_agent" / "api" / "chat.py"
    src = chat_file.read_text(encoding="utf-8")
    assert "llm_service.send_request" not in src
    assert "tool_registry.execute" not in src


def test_bootstrap_uses_guarded_handler_for_vanna_routes() -> None:
    bootstrap = (REPO_ROOT / "src" / "vai_agent" / "bootstrap.py").read_text(encoding="utf-8")
    assert "GuardedChatHandler" in bootstrap
    assert "register_chat_routes" in bootstrap
    assert "ChatHandler(runtime.vanna)" not in bootstrap


@pytest.mark.skipif(
    (REPO_ROOT / ".env").is_file(),
    reason="Local .env present — skip committed-secret probe",
)
def test_dotenv_not_present_for_delivery_probe() -> None:
    assert not (REPO_ROOT / ".env").is_file()
