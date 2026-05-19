"""Tests for :mod:`vai_agent.db.sql_alias_guard`."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from vai_agent.db.mssql_runner import ConnectionPool, MssqlRunner
from vai_agent.db.sql_alias_guard import normalize_sql_aliases


def test_rowcount_alias_bracketed() -> None:
    sql = "SELECT COUNT(*) AS RowCount FROM dbo.Suppliers"
    assert "[record_count]" in normalize_sql_aliases(sql)
    assert "RowCount" not in normalize_sql_aliases(sql)


def test_rowcount_alias_quoted() -> None:
    sql = "SELECT COUNT(*) AS [RowCount] FROM dbo.Suppliers"
    out = normalize_sql_aliases(sql)
    assert "AS [record_count]" in out


def test_safe_sql_unchanged() -> None:
    sql = "SELECT COUNT(*) AS [record_count] FROM dbo.Suppliers"
    assert normalize_sql_aliases(sql) == sql


def test_mssql_runner_calls_normalizer_before_execute() -> None:
    from vai_agent.db.connection import ConnectionSettings

    settings = ConnectionSettings(  # type: ignore[call-arg]
        host="h",
        database="d",
        username="u",
        password="p",
        trust_server_certificate=True,
        _env_file=None,
    )
    runner = MssqlRunner(settings, max_rows=10, query_timeout=1)
    MssqlRunner._pool = None
    cur = MagicMock()
    cur.description = [("record_count",)]
    cur.fetchmany.return_value = [(29,)]
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def _pool_cm(*_a, **_kw):
        try:
            yield conn
        except Exception:
            conn.close()
            raise

    with (
        patch.object(
            ConnectionPool,
            "get_connection",
            side_effect=_pool_cm,
        ),
        patch("vai_agent.db.mssql_runner.get_activity_recorder", return_value=None),
        patch("vai_agent.db.mssql_runner.normalize_sql_aliases") as norm,
    ):
        norm.side_effect = lambda s: s.replace("AS RowCount", "AS [record_count]")
        runner.execute("SELECT 1 AS RowCount FROM t")

    norm.assert_called_once_with("SELECT 1 AS RowCount FROM t")
    cur.execute.assert_called_once_with("SELECT 1 AS [record_count] FROM t")
