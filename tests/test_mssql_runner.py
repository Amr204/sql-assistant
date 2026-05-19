"""Tests for :mod:`vai_agent.db.mssql_runner`.

All database I/O is mocked. No real SQL Server connection is needed.

Mocking strategy
----------------
:class:`~vai_agent.db.mssql_runner.ConnectionPool.get_connection` is patched
to yield a ``MagicMock`` connection whose ``cursor()`` returns a mock cursor
with ``description``, ``execute``, and ``fetchmany`` behaviour matching pyodbc.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pyodbc
import pytest

from vai_agent.db.connection import ConnectionSettings
from vai_agent.db.mssql_runner import (
    ConnectionPool,
    MssqlRunner,
    QueryResult,
    QueryTimeoutError,
    RunnerError,
    _normalise_value,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings() -> ConnectionSettings:
    return ConnectionSettings(  # type: ignore[call-arg]
        host="localhost",
        database="TestDB",
        username="reader",
        password="pass",
        trust_server_certificate=True,
        _env_file=None,
    )


def _runner(max_rows: int = 100, query_timeout: int = 30) -> MssqlRunner:
    return MssqlRunner(_settings(), max_rows=max_rows, query_timeout=query_timeout)


@contextmanager
def _pool_context_like(conn: MagicMock):
    """Mimic :meth:`ConnectionPool.get_connection` cleanup on query failure."""

    try:
        yield conn
    except Exception:
        conn.close()
        raise


def _patch_pool_conn(conn: MagicMock):
    """Patch pool context manager to yield *conn* (class pool is reset per test)."""

    MssqlRunner._pool = None
    return patch.object(
        ConnectionPool,
        "get_connection",
        side_effect=lambda *_a, **_kw: _pool_context_like(conn),
    )


def _cursor_from_batches(
    columns: list[str] | None,
    *batches: list[tuple[Any, ...]],
) -> MagicMock:
    """Each positional after *columns* is one batch from ``fetchmany``."""
    cur = MagicMock()
    cur.description = [(c,) for c in columns] if columns is not None else None
    queue: list[list[tuple[Any, ...]]] = [list(b) for b in batches]

    def fetchmany(_size: int) -> list[tuple[Any, ...]]:
        return queue.pop(0) if queue else []

    cur.fetchmany.side_effect = fetchmany
    cur.execute = MagicMock()
    return cur


def _conn_with_cursor(cursor: MagicMock) -> MagicMock:
    conn = MagicMock(spec=pyodbc.Connection)
    conn.cursor.return_value = cursor
    conn.close = MagicMock()
    return conn


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_max_rows_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="max_rows"):
            MssqlRunner(_settings(), max_rows=0)

    def test_query_timeout_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError, match="query_timeout"):
            MssqlRunner(_settings(), query_timeout=-1)

    def test_zero_timeout_allowed(self) -> None:
        runner = MssqlRunner(_settings(), query_timeout=0)
        assert runner._query_timeout == 0


# ---------------------------------------------------------------------------
# No pandas in runner
# ---------------------------------------------------------------------------


class TestNoPandasReadSql:
    def test_module_source_has_no_pandas_read_sql(self) -> None:
        import vai_agent.db.mssql_runner as m

        src = Path(m.__file__).read_text(encoding="utf-8")
        assert "read_sql" not in src
        assert "pandas" not in src


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_query_result(self) -> None:
        cur = _cursor_from_batches(
            ["CustomerID", "Name"],
            [("A", "Alice"), ("B", "Bob")],
        )
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner().execute("SELECT CustomerID, Name FROM dbo.Customers")

        assert isinstance(result, QueryResult)
        assert result.columns == ["CustomerID", "Name"]
        assert result.row_count == 2
        assert result.rows[0] == {"CustomerID": "A", "Name": "Alice"}
        assert result.truncated is False
        assert cur.execute.call_count >= 1
        assert cur.fetchmany.call_count >= 1

    def test_empty_result_set(self) -> None:
        cur = _cursor_from_batches(["id"], [])
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner().execute("SELECT id FROM t WHERE 1=0")

        assert result.row_count == 0
        assert result.rows == []
        assert result.columns == ["id"]

    def test_no_description_returns_empty(self) -> None:
        cur = MagicMock()
        cur.description = None
        cur.execute = MagicMock()
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner().execute("INSERT INTO t VALUES (1)")

        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0
        cur.fetchmany.assert_not_called()

    def test_rewritten_sql_stored(self) -> None:
        cur = _cursor_from_batches(["x"], [(1,)])
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner().execute(
                "SELECT TOP 1 x FROM t",
                rewritten_sql="SELECT TOP 1 x FROM t",
            )

        assert result.rewritten_sql == "SELECT TOP 1 x FROM t"

    def test_connection_closed_after_success(self) -> None:
        cur = _cursor_from_batches(["a"], [(1,)])
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            _runner().execute("SELECT a FROM t")

        conn.close.assert_not_called()


# ---------------------------------------------------------------------------
# Row cap
# ---------------------------------------------------------------------------


class TestRowCap:
    def test_truncates_when_single_chunk_exceeds_max(self) -> None:
        cur = _cursor_from_batches(
            ["id"],
            [(1,), (2,), (3,), (4,), (5,)],
        )
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner(max_rows=3).execute("SELECT id FROM t")

        assert result.row_count == 3
        assert result.truncated is True
        assert [r["id"] for r in result.rows] == [1, 2, 3]

    def test_truncates_across_multiple_chunks(self) -> None:
        cur = _cursor_from_batches(
            ["id"],
            [(1,), (2,), (3,)],
            [(4,), (5,), (6,)],
        )
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner(max_rows=4).execute("SELECT id FROM t")

        assert result.row_count == 4
        assert result.truncated is True
        assert [r["id"] for r in result.rows] == [1, 2, 3, 4]
        assert cur.fetchmany.call_count >= 2

    def test_exactly_max_rows_sets_truncated(self) -> None:
        cur = _cursor_from_batches(
            ["id"],
            [(0,), (1,), (2,), (3,), (4,)],
        )
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner(max_rows=5).execute("SELECT id FROM t")

        assert result.row_count == 5
        assert result.truncated is True


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestQueryTimeout:
    @staticmethod
    def _timeout_exc() -> pyodbc.Error:
        return pyodbc.Error("HYT00", "[HYT00] Query timeout expired")

    def test_timeout_raises_query_timeout_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = self._timeout_exc()
        conn = _conn_with_cursor(cur)

        with (
            _patch_pool_conn(conn),
            pytest.raises(QueryTimeoutError) as exc_info,
        ):
            _runner(query_timeout=5).execute("SELECT id FROM t")

        assert "5-second" in exc_info.value.safe_message

    def test_connection_closed_after_timeout(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = self._timeout_exc()
        conn = _conn_with_cursor(cur)

        with (
            _patch_pool_conn(conn),
            pytest.raises(QueryTimeoutError),
        ):
            _runner().execute("SELECT id FROM t")

        conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# Generic DB errors
# ---------------------------------------------------------------------------


class TestDbErrors:
    def test_pyodbc_error_raises_runner_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = pyodbc.Error("42000", "[42000] Syntax error near 'x'")
        conn = _conn_with_cursor(cur)

        with (
            _patch_pool_conn(conn),
            pytest.raises(RunnerError) as exc_info,
        ):
            _runner().execute("SELECT xyz FROMM t")

        assert "42000" not in exc_info.value.safe_message
        assert "Syntax error" not in exc_info.value.safe_message

    def test_runner_error_has_debug_hint(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = pyodbc.Error("42000", "[42000] Column 'x' not found")
        conn = _conn_with_cursor(cur)

        with (
            _patch_pool_conn(conn),
            pytest.raises(RunnerError) as exc_info,
        ):
            _runner().execute("SELECT x FROM t")

        assert exc_info.value.debug_hint != ""

    def test_connection_error_raises_runner_error(self) -> None:
        exc = pyodbc.Error("08001", "[08001] Cannot connect")

        with (
            patch("vai_agent.db.mssql_runner.pyodbc.connect", side_effect=exc),
            pytest.raises(RunnerError) as exc_info,
        ):
            _runner().execute("SELECT 1")

        assert "08001" not in exc_info.value.safe_message

    def test_connection_closed_after_generic_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = pyodbc.Error("42000", "err")
        conn = _conn_with_cursor(cur)

        with (
            _patch_pool_conn(conn),
            pytest.raises(RunnerError),
        ):
            _runner().execute("SELECT 1")

        conn.close.assert_called_once()

    def test_unexpected_exception_raises_runner_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("unexpected!")
        conn = _conn_with_cursor(cur)

        with (
            _patch_pool_conn(conn),
            pytest.raises(RunnerError),
        ):
            _runner().execute("SELECT 1")


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------


class TestNormaliseValue:
    def test_none_stays_none(self) -> None:
        assert _normalise_value(None) is None

    def test_float_nan_becomes_none(self) -> None:
        assert _normalise_value(float("nan")) is None

    def test_datetime_becomes_iso_string(self) -> None:
        dt = datetime(2026, 5, 16, 10, 0, 0)
        result = _normalise_value(dt)
        assert isinstance(result, str)
        assert "2026-05-16" in result

    def test_date_becomes_iso_string(self) -> None:
        from datetime import date as date_cls

        d = date_cls(2026, 3, 1)
        result = _normalise_value(d)
        assert result == "2026-03-01"

    def test_int_stays_int(self) -> None:
        assert _normalise_value(42) == 42

    def test_string_stays_string(self) -> None:
        assert _normalise_value("hello") == "hello"

    def test_numpy_int_becomes_python_int(self) -> None:
        val = _normalise_value(np.int64(7))
        assert val == 7
        assert isinstance(val, int)

    def test_numpy_float_becomes_python_float(self) -> None:
        val = _normalise_value(np.float64(3.14))
        assert abs(val - 3.14) < 1e-9
        assert isinstance(val, float)

    def test_numpy_float_nan_becomes_none(self) -> None:
        assert _normalise_value(np.float64(float("nan"))) is None

    def test_bytes_encoded_base64(self) -> None:
        import base64

        raw = b"hello"
        assert _normalise_value(raw) == base64.b64encode(raw).decode("ascii")

    def test_decimal_to_float(self) -> None:
        from decimal import Decimal

        assert _normalise_value(Decimal("3.5")) == 3.5


# ---------------------------------------------------------------------------
# QueryResult model
# ---------------------------------------------------------------------------


class TestQueryResultModel:
    def test_result_is_frozen(self) -> None:
        from pydantic import ValidationError

        r = QueryResult(columns=["a"], rows=[{"a": 1}], row_count=1)
        with pytest.raises(ValidationError):
            r.columns = ["b"]  # type: ignore[misc]

    def test_truncated_defaults_false(self) -> None:
        r = QueryResult(columns=[], rows=[], row_count=0)
        assert r.truncated is False

    def test_rewritten_sql_defaults_none(self) -> None:
        r = QueryResult(columns=[], rows=[], row_count=0)
        assert r.rewritten_sql is None


# ---------------------------------------------------------------------------
# Multi-type column result
# ---------------------------------------------------------------------------


class TestMixedTypes:
    def test_mixed_columns_normalised(self) -> None:
        cur = _cursor_from_batches(
            ["id", "name", "score", "ts"],
            [
                (np.int64(1), "Alice", 9.5, datetime(2026, 1, 1, 0, 0)),
                (np.int64(2), None, float("nan"), None),
            ],
        )
        conn = _conn_with_cursor(cur)

        with _patch_pool_conn(conn):
            result = _runner().execute("SELECT id, name, score, ts FROM t")

        r0, r1 = result.rows
        assert r0["id"] == 1 and isinstance(r0["id"], int)
        assert r0["name"] == "Alice"
        assert abs(r0["score"] - 9.5) < 1e-9
        assert "2026-01-01" in r0["ts"]
        assert r1["name"] is None
        assert r1["score"] is None
        assert r1["ts"] is None
