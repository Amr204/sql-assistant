"""Tests for :mod:`vai_agent.db.mssql_runner`.

All database I/O is mocked. No real SQL Server connection is needed.

Mocking strategy
----------------
``MssqlRunner._connect`` is patched to return a ``MagicMock`` (acts as
a DBAPI connection). ``pandas.read_sql`` is patched to return a
controllable iterator of DataFrames, letting each test scenario drive
the exact data shape without touching a database.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pyodbc
import pytest

from vai_agent.db.connection import ConnectionSettings
from vai_agent.db.mssql_runner import (
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
    )


def _runner(max_rows: int = 100, query_timeout: int = 30) -> MssqlRunner:
    return MssqlRunner(_settings(), max_rows=max_rows, query_timeout=query_timeout)


def _mock_conn() -> MagicMock:
    conn = MagicMock(spec=pyodbc.Connection)
    conn.close = MagicMock()
    return conn


def _df(data: dict[str, list]) -> pd.DataFrame:
    return pd.DataFrame(data)


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
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_returns_query_result(self) -> None:
        df = _df({"CustomerID": ["A", "B"], "Name": ["Alice", "Bob"]})
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            result = _runner().execute("SELECT CustomerID, Name FROM dbo.Customers")

        assert isinstance(result, QueryResult)
        assert result.columns == ["CustomerID", "Name"]
        assert result.row_count == 2
        assert result.rows[0] == {"CustomerID": "A", "Name": "Alice"}
        assert result.truncated is False

    def test_empty_result_set(self) -> None:
        df = _df({"id": []})
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            result = _runner().execute("SELECT id FROM t WHERE 1=0")

        assert result.row_count == 0
        assert result.rows == []
        assert result.columns == ["id"]

    def test_rewritten_sql_stored(self) -> None:
        df = _df({"x": [1]})
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            result = _runner().execute(
                "SELECT TOP 1 x FROM t", rewritten_sql="SELECT TOP 1 x FROM t"
            )

        assert result.rewritten_sql == "SELECT TOP 1 x FROM t"

    def test_connection_closed_after_success(self) -> None:
        df = _df({"a": [1]})
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            _runner().execute("SELECT a FROM t")

        conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# Row cap
# ---------------------------------------------------------------------------

class TestRowCap:
    def test_truncates_when_single_chunk_exceeds_max(self) -> None:
        df = _df({"id": [1, 2, 3, 4, 5]})
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            result = _runner(max_rows=3).execute("SELECT id FROM t")

        assert result.row_count == 3
        assert result.truncated is True
        assert [r["id"] for r in result.rows] == [1, 2, 3]

    def test_truncates_across_multiple_chunks(self) -> None:
        chunks = [_df({"id": [1, 2, 3]}), _df({"id": [4, 5, 6]})]
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter(chunks)),
        ):
            result = _runner(max_rows=4).execute("SELECT id FROM t")

        assert result.row_count == 4
        assert result.truncated is True
        assert [r["id"] for r in result.rows] == [1, 2, 3, 4]

    def test_exactly_max_rows_sets_truncated(self) -> None:
        # When we hit exactly max_rows we stop reading further chunks.
        # truncated=True is the conservative, correct signal — the caller
        # cannot know whether additional rows exist without fetching them.
        df = _df({"id": list(range(5))})
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            result = _runner(max_rows=5).execute("SELECT id FROM t")

        assert result.row_count == 5
        assert result.truncated is True  # conservative: stopped at cap boundary


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestQueryTimeout:
    @staticmethod
    def _timeout_exc() -> pyodbc.Error:
        return pyodbc.Error("HYT00", "[HYT00] Query timeout expired")

    def test_timeout_raises_query_timeout_error(self) -> None:
        conn = _mock_conn()
        exc = self._timeout_exc()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", side_effect=exc),
            pytest.raises(QueryTimeoutError) as exc_info,
        ):
            _runner(query_timeout=5).execute("SELECT id FROM t")

        assert "5-second" in exc_info.value.safe_message

    def test_connection_closed_after_timeout(self) -> None:
        conn = _mock_conn()
        exc = self._timeout_exc()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", side_effect=exc),
            pytest.raises(QueryTimeoutError),
        ):
            _runner().execute("SELECT id FROM t")

        conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# Generic DB errors
# ---------------------------------------------------------------------------

class TestDbErrors:
    def test_pyodbc_error_raises_runner_error(self) -> None:
        conn = _mock_conn()
        exc = pyodbc.Error("42000", "[42000] Syntax error near 'x'")

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", side_effect=exc),
            pytest.raises(RunnerError) as exc_info,
        ):
            _runner().execute("SELECT xyz FROMM t")

        assert "42000" not in exc_info.value.safe_message
        assert "Syntax error" not in exc_info.value.safe_message

    def test_runner_error_has_debug_hint(self) -> None:
        conn = _mock_conn()
        exc = pyodbc.Error("42000", "[42000] Column 'x' not found")

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", side_effect=exc),
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
        conn = _mock_conn()
        exc = pyodbc.Error("42000", "err")

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", side_effect=exc),
            pytest.raises(RunnerError),
        ):
            _runner().execute("SELECT 1")

        conn.close.assert_called_once()

    def test_unexpected_exception_raises_runner_error(self) -> None:
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch(
                "vai_agent.db.mssql_runner.pd.read_sql",
                side_effect=RuntimeError("unexpected!"),
            ),
            pytest.raises(RunnerError),
        ):
            _runner().execute("SELECT 1")


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------

class TestNormaliseValue:
    def test_none_stays_none(self) -> None:
        assert _normalise_value(None) is None

    def test_nat_becomes_none(self) -> None:
        assert _normalise_value(pd.NaT) is None

    def test_float_nan_becomes_none(self) -> None:
        assert _normalise_value(float("nan")) is None

    def test_timestamp_becomes_iso_string(self) -> None:
        ts = pd.Timestamp("2026-05-16 10:00:00")
        result = _normalise_value(ts)
        assert isinstance(result, str)
        assert "2026-05-16" in result

    def test_int_stays_int(self) -> None:
        assert _normalise_value(42) == 42

    def test_string_stays_string(self) -> None:
        assert _normalise_value("hello") == "hello"

    def test_numpy_int_becomes_python_int(self) -> None:
        import numpy as np
        val = _normalise_value(np.int64(7))
        assert val == 7
        assert isinstance(val, int)

    def test_numpy_float_becomes_python_float(self) -> None:
        import numpy as np
        val = _normalise_value(np.float64(3.14))
        assert abs(val - 3.14) < 1e-9
        assert isinstance(val, float)


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
        df = pd.DataFrame({
            "id": pd.array([1, 2], dtype="int64"),
            "name": ["Alice", None],
            "score": [9.5, float("nan")],
            "ts": [pd.Timestamp("2026-01-01"), pd.NaT],
        })
        conn = _mock_conn()

        with (
            patch.object(MssqlRunner, "_connect", return_value=conn),
            patch("vai_agent.db.mssql_runner.pd.read_sql", return_value=iter([df])),
        ):
            result = _runner().execute("SELECT id, name, score, ts FROM t")

        r0, r1 = result.rows
        assert r0["id"] == 1 and isinstance(r0["id"], int)
        assert r0["name"] == "Alice"
        assert abs(r0["score"] - 9.5) < 1e-9
        assert "2026-01-01" in r0["ts"]
        assert r1["name"] is None
        assert r1["score"] is None
        assert r1["ts"] is None
