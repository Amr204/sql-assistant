"""Guards against reintroducing non-Vanna primary runtime wiring in ``src``."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAT = REPO_ROOT / "src" / "vai_agent" / "api" / "chat.py"
BOOT = REPO_ROOT / "src" / "vai_agent" / "bootstrap.py"


def test_chat_does_not_wire_legacy_openrouter_state() -> None:
    assert "app.state.llm_service" not in CHAT.read_text(encoding="utf-8")


def test_bootstrap_does_not_set_app_state_llm_service() -> None:
    text = BOOT.read_text(encoding="utf-8")
    assert "app.state.llm_service" not in text
    assert "build_chat_completion_client" not in text
