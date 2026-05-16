"""SecureRunSqlTool — the gated execution path for user-supplied SQL.

Pipeline (every step must pass before the next):

1. :class:`~vai_agent.security.sql_policy.SqlPolicyEngine.validate` —
   structural checks (DML/DDL block, SELECT *, blocked schemas, …)
2. :class:`~vai_agent.security.pii_policy.PiiPolicyEngine.check` —
   column-level sensitivity (PII / secret / sensitive).
3. :meth:`~vai_agent.db.mssql_runner.MssqlRunner.execute` — actual
   execution with per-query timeout and row cap.

If any step fails, a :class:`ToolResult` with ``success=False`` and a
sanitised error message is returned. The raw exception is never
propagated to the caller.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from vai_agent.db.mssql_runner import (
    MssqlRunner,
    QueryTimeoutError,
    RunnerError,
)
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.sql_policy import SqlPolicyEngine
from vai_agent.tools.base import ToolBase, ToolResult

if TYPE_CHECKING:
    from vai_agent.users import User

logger = logging.getLogger(__name__)


class SecureRunSqlArgs(BaseModel):
    """Arguments for :class:`SecureRunSqlTool`."""

    sql: str = Field(min_length=1, description="The SQL SELECT statement to run.")


class SecureRunSqlTool(ToolBase):
    """Validate and execute a single read-only SELECT query."""

    name = "secure_run_sql"
    description = (
        "Validate and run a single read-only SELECT statement against the "
        "configured SQL Server database. The query is rejected if it "
        "contains DML/DDL, multi-statement input, blocked schemas/tables, "
        "or references to columns marked sensitive."
    )
    args_model = SecureRunSqlArgs
    # An empty tuple means any authenticated user may invoke. Per-column
    # access is still enforced by ``PiiPolicyEngine``.
    access_groups: tuple[str, ...] = ()

    def __init__(
        self,
        sql_policy: SqlPolicyEngine,
        pii_policy: PiiPolicyEngine,
        runner: MssqlRunner,
    ) -> None:
        self._sql_policy = sql_policy
        self._pii_policy = pii_policy
        self._runner = runner

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        if not isinstance(args, SecureRunSqlArgs):  # pragma: no cover - guarded by Agent
            return self._fail("Invalid arguments.")

        sql_result = self._sql_policy.validate(args.sql, user_groups=list(user.groups))
        if not sql_result.allowed:
            logger.info(
                "secure_run_sql blocked by SQL policy",
                extra={
                    "user_id": user.id,
                    "codes": [v.code for v in sql_result.violations],
                },
            )
            return self._fail(
                "Query was rejected by the SQL policy.",
                violations=[v.model_dump() for v in sql_result.violations],
                stage="sql_policy",
            )

        pii_result = self._pii_policy.check(args.sql, user_groups=list(user.groups))
        if not pii_result.allowed:
            logger.info(
                "secure_run_sql blocked by PII policy",
                extra={
                    "user_id": user.id,
                    "codes": [v.code for v in pii_result.violations],
                },
            )
            return self._fail(
                "Query was rejected by the data-protection policy.",
                violations=[v.model_dump() for v in pii_result.violations],
                stage="pii_policy",
            )

        # The SQL is approved — run it via the safe runner.
        sql_to_run = sql_result.rewritten_sql or args.sql
        try:
            query_result = self._runner.execute(
                sql_to_run, rewritten_sql=sql_result.rewritten_sql,
            )
        except QueryTimeoutError as exc:
            return self._fail(exc.safe_message, stage="execute")
        except RunnerError as exc:
            return self._fail(exc.safe_message, stage="execute")

        return self._ok(
            query_result.model_dump(),
            stage="execute",
            # Surface warnings (e.g. PII004 heuristic hits) for observability,
            # but never the policy-blocked errors (those would not reach here).
            warnings=[
                v.model_dump() for v in pii_result.violations if v.severity == "warning"
            ],
        )
