"""Makefile reload flags for uvicorn."""

from __future__ import annotations

from pathlib import Path


def test_run_api_includes_reload_dirs_and_excludes() -> None:
    text = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
    assert "--reload-dir src" in text
    assert "--reload-dir profiles" in text
    assert "logs/*" in text
    assert "activity_audit" in text
    assert "run-api:" in text
    assert "$(RELOAD_FLAGS)" in text
    assert "run:" in text
    assert text.count("$(RELOAD_FLAGS)") >= 2
