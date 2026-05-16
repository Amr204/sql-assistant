"""Tests for :class:`vai_agent.tools.SecureRunSqlTool`.

The pipeline (sql_policy → pii_policy → runner) is unit-tested here
with real policy engines and a mocked runner. Each policy engine is
already tested in isolation; this test class verifies the wiring.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vai_agent.db.mssql_runner import (
    MssqlRunner,
    QueryResult,
    QueryTimeoutError,
    RunnerError,
)
from vai_agent.knowledge.profile_models import SecurityPolicy
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.sql_policy import SqlPolicyEngine
from vai_agent.tools.secure_run_sql_tool import SecureRunSqlArgs, SecureRunSqlTool
from vai_agent.users import User


def _tool(
    *,
    pii_columns: list[str] | None = None,
    secret_columns: list[str] | None = None,
    max_rows: int = 500,
    runner: MssqlRunner | None = None,
) -> tuple[SecureRunSqlTool, MagicMock]:
    policy = SecurityPolicy(
        pii_columns=pii_columns or [],
        secret_columns=secret_columns or [],
        max_rows=max_rows,
    )
    runner = runner or MagicMock(spec=MssqlRunner)
    tool = SecureRunSqlTool(
        sql_policy=SqlPolicyEngine(policy),
        pii_policy=PiiPolicyEngine(policy),
        runner=runner,
    )
    return tool, runner


def _user(groups: tuple[str, ...] = ()) -> User:
    return User(id="u", groups=groups)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_runs_safe_query(self) -> None:
        tool, runner = _tool()
        runner.execute.return_value = QueryResult(
            columns=["CustomerID"],
            rows=[{"CustomerID": "A"}],
            row_count=1,
            rewritten_sql="SELECT TOP 500 CustomerID FROM dbo.Customers",
        )
        args = SecureRunSqlArgs(sql="SELECT CustomerID FROM dbo.Customers")
        result = tool.execute(args, _user())
        assert result.success
        assert result.data["row_count"] == 1
        runner.execute.assert_called_once()

    def test_passes_rewritten_sql_to_runner(self) -> None:
        tool, runner = _tool(max_rows=10)
        runner.execute.return_value = QueryResult(columns=[], rows=[], row_count=0)
        tool.execute(SecureRunSqlArgs(sql="SELECT CustomerID FROM dbo.Customers"), _user())
        sent_sql = runner.execute.call_args.args[0]
        assert "TOP 10" in sent_sql.upper()


# ---------------------------------------------------------------------------
# SQL policy stage
# ---------------------------------------------------------------------------


class TestBlockedBySqlPolicy:
    def test_delete_blocked(self) -> None:
        tool, runner = _tool()
        result = tool.execute(SecureRunSqlArgs(sql="DELETE FROM Customers"), _user())
        assert not result.success
        assert result.metadata["stage"] == "sql_policy"
        runner.execute.assert_not_called()

    def test_select_star_blocked(self) -> None:
        tool, _runner = _tool()
        result = tool.execute(SecureRunSqlArgs(sql="SELECT * FROM Customers"), _user())
        assert not result.success
        assert result.metadata["stage"] == "sql_policy"
        codes = {v["code"] for v in result.metadata["violations"]}
        assert "POL003" in codes

    def test_runner_not_invoked_on_block(self) -> None:
        tool, runner = _tool()
        tool.execute(SecureRunSqlArgs(sql="DROP TABLE x"), _user())
        runner.execute.assert_not_called()


# ---------------------------------------------------------------------------
# PII policy stage
# ---------------------------------------------------------------------------


class TestBlockedByPiiPolicy:
    def test_secret_column_blocked(self) -> None:
        tool, runner = _tool(secret_columns=["Employees.BirthDate"])
        result = tool.execute(
            SecureRunSqlArgs(sql="SELECT BirthDate FROM dbo.Employees"),
            _user(),
        )
        assert not result.success
        assert result.metadata["stage"] == "pii_policy"
        runner.execute.assert_not_called()

    def test_pii_warning_surfaces_in_metadata_when_query_succeeds(self) -> None:
        # No policy entry for Phone, but the heuristic flags it as a warning.
        tool, runner = _tool()
        runner.execute.return_value = QueryResult(columns=["Phone"], rows=[], row_count=0)
        result = tool.execute(
            SecureRunSqlArgs(sql="SELECT Phone FROM dbo.Customers"),
            _user(),
        )
        assert result.success
        warnings = result.metadata.get("warnings", [])
        codes = {w["code"] for w in warnings}
        assert "PII004" in codes


# ---------------------------------------------------------------------------
# Runner errors
# ---------------------------------------------------------------------------


class TestRunnerErrors:
    def test_timeout_is_returned_as_failure(self) -> None:
        runner = MagicMock(spec=MssqlRunner)
        runner.execute.side_effect = QueryTimeoutError("Query exceeded the 5-second time limit.")
        tool, _ = _tool(runner=runner)
        result = tool.execute(SecureRunSqlArgs(sql="SELECT CustomerID FROM dbo.Customers"), _user())
        assert not result.success
        assert "5-second" in result.error
        assert result.metadata["stage"] == "execute"

    def test_runner_error_is_returned_as_failure(self) -> None:
        runner = MagicMock(spec=MssqlRunner)
        runner.execute.side_effect = RunnerError("Could not connect to the database. Please try again later.")
        tool, _ = _tool(runner=runner)
        result = tool.execute(SecureRunSqlArgs(sql="SELECT CustomerID FROM dbo.Customers"), _user())
        assert not result.success
        assert "connect" in result.error.lower()


# ---------------------------------------------------------------------------
# Argument model
# ---------------------------------------------------------------------------


class TestArgs:
    def test_empty_sql_rejected_at_arg_model(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SecureRunSqlArgs(sql="")
