"""Vanna SQL tools use structured results (no CSV file storage setting)."""

from __future__ import annotations

from vai_agent.config.settings import Settings


def test_settings_no_csv_file_storage_dir() -> None:
    """CSV export path settings were removed; SQL results are structured in-app."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "vanna_file_storage_dir" not in Settings.model_fields
