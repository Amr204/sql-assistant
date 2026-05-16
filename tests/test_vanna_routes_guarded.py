"""Vanna stock FastAPI routes must use the guarded chat handler."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_registers_guarded_vanna_routes() -> None:
    text = (REPO_ROOT / "src" / "vai_agent" / "bootstrap.py").read_text(encoding="utf-8")
    assert "GuardedChatHandler(runtime.vanna, settings)" in text
    assert "vanna_fastapi_routes import register_chat_routes" in text
