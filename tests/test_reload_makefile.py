"""Dev server reload settings (Windows-safe via uvicorn.run)."""

from __future__ import annotations

from pathlib import Path


def test_run_api_module_defines_reload_dirs_and_excludes() -> None:
    text = (Path(__file__).resolve().parents[1] / "src/vai_agent/cli/run_api.py").read_text(
        encoding="utf-8"
    )
    assert 'RELOAD_DIRS = ["src", "profiles"]' in text
    assert '"logs/*"' in text
    assert '"activity_audit/*"' in text
    assert "uvicorn.run(" in text


def test_dev_launches_run_api_module_not_uvicorn_cli() -> None:
    text = (Path(__file__).resolve().parents[1] / "src/vai_agent/cli/dev.py").read_text(
        encoding="utf-8"
    )
    assert '"-m", "vai_agent.cli.run_api"' in text
    assert "--reload-exclude" not in text
