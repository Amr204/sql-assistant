"""Vanna SQL tools use :class:`~vai_agent.vanna_integration.vai_run_sql_tool.VaiRunSqlTool` (structured, no CSV)."""

from __future__ import annotations

from vai_agent.config.settings import Settings


def test_vanna_file_storage_default_under_dot_data() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vanna_file_storage_dir.startswith(".data/")
    assert "vanna_files" in s.vanna_file_storage_dir

# Legacy CSV export path removed from factory; settings key kept for compatibility.

