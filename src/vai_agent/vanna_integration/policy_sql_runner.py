"""``SqlRunner`` that enforces ``SqlPolicyEngine`` / ``PiiPolicyEngine`` before ``MssqlRunner``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd
import sqlglot
import sqlglot.errors
from vanna.capabilities.sql_runner import SqlRunner
from vanna.capabilities.sql_runner.models import RunSqlToolArgs
from vanna.core.tool import ToolContext

from vai_agent.db.mssql_runner import MssqlRunner, RunnerError
from vai_agent.db.mssql_runner import QueryTimeoutError as DbQueryTimeoutError
from vai_agent.knowledge.profile_models import Profile, SecurityPolicy
from vai_agent.security.audit_log import emit_tool_audit, sql_fingerprint
from vai_agent.security.pii_policy import PiiCheckResult, PiiPolicyEngine
from vai_agent.security.result_policy import apply_masking_rules, enforce_min_group_size
from vai_agent.security.sql_policy import SqlPolicyEngine, SqlPolicyResult
from vai_agent.users import User as VaiUser
from vai_agent.vanna_integration.errors import (
    PolicyRejectedError,
    QueryRejectedError,
    RequestCancelledError,
    SqlRunnerTimeoutError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _parse_sql_once(sql: str) -> list[Any] | None:
    """Parse SQL once using sqlglot T-SQL dialect (matches policy engines)."""

    try:
        return sqlglot.parse(
            sql.strip(),
            read="tsql",
            error_level=sqlglot.errors.ErrorLevel.WARN,
        )
    except Exception:
        return None


def _is_cancelled(context: ToolContext) -> bool:
    md = context.metadata or {}
    if md.get("cancelled") is True:
        return True
    return getattr(context, "cancelled", False) is True


def _question_from_tool_context(context: ToolContext) -> str:
    """Best-effort natural language question for auto-learn and audit."""

    md = context.metadata or {}
    original = md.get("original_question")
    if isinstance(original, str) and original.strip():
        return original.strip()
    for key in ("message", "question", "user_message"):
        raw = md.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


@dataclass(frozen=True)
class StructuredSqlRun:
    """Policy-checked SQL outcome without a pandas ``DataFrame``."""

    sql_executed: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


def _to_vai_user(context: ToolContext) -> VaiUser:
    u = context.user
    return VaiUser(
        id=u.id,
        email=u.email,
        groups=tuple(u.group_memberships),
    )


class PolicySqlRunner(SqlRunner):
    """Runs approved SELECT queries only; maps Vanna :class:`ToolContext` users."""

    def __init__(
        self,
        sql_policy: SqlPolicyEngine,
        pii_policy: PiiPolicyEngine,
        runner: MssqlRunner,
        *,
        security_policy: SecurityPolicy,
        profile: Profile | None = None,
    ) -> None:
        self._sql_policy = sql_policy
        self._pii_policy = pii_policy
        self._runner = runner
        self._security_policy = security_policy
        self._profile = profile
        self._auto_learn_callback: Callable[[str, str, int], None] | None = None

    def set_auto_learn_callback(self, callback: Callable[[str, str, int], None] | None) -> None:
        """Set callback invoked after successful SQL execution (question, sql, row_count)."""

        self._auto_learn_callback = callback

    async def validate_tool_sql(
        self,
        sql: str,
        context: ToolContext,
    ) -> tuple[SqlPolicyResult, PiiCheckResult]:
        """Run SQL + PII policy checks only (no database execution)."""

        user = _to_vai_user(context)
        groups = list(user.groups)

        def _validate_sql() -> tuple[SqlPolicyResult, PiiCheckResult]:
            parsed = _parse_sql_once(sql)
            return (
                self._sql_policy.validate(sql, user_groups=groups, parsed_ast=parsed),
                self._pii_policy.check(sql, user_groups=groups, parsed_ast=parsed),
            )

        sql_result, pii_result = await asyncio.to_thread(_validate_sql)
        return sql_result, pii_result

    async def execute_structured_approved(
        self,
        args: RunSqlToolArgs,
        context: ToolContext,
        sql_result: SqlPolicyResult,
        pii_result: PiiCheckResult,
    ) -> StructuredSqlRun:
        """Run the database query after a successful :meth:`validate_tool_sql` (no re-validation)."""

        user = _to_vai_user(context)
        rid = context.request_id
        return await self._execute_structured(args, context, sql_result, pii_result, user, rid)

    async def run_sql_structured(
        self,
        args: RunSqlToolArgs,
        context: ToolContext,
    ) -> StructuredSqlRun:
        """Validate and execute SQL; return rows/columns without building a ``DataFrame``."""

        if _is_cancelled(context):
            raise RequestCancelledError()

        sql_result, pii_result = await self.validate_tool_sql(args.sql, context)
        user = _to_vai_user(context)
        groups = list(user.groups)
        rid = context.request_id

        original_question = _question_from_tool_context(context)

        if not sql_result.allowed:
            emit_tool_audit(
                request_id=rid,
                user_id=user.id,
                access_groups=groups,
                tool_name="run_sql",
                decision="rejected",
                sql_hash=sql_fingerprint(args.sql),
                violations=[v.model_dump() for v in sql_result.violations],
                error_code="sql_policy",
                question=original_question or None,
            )
            msg = "Query was rejected by the SQL policy."
            raise PolicyRejectedError(msg)

        if not pii_result.allowed:
            emit_tool_audit(
                request_id=rid,
                user_id=user.id,
                access_groups=groups,
                tool_name="run_sql",
                decision="rejected",
                sql_hash=sql_fingerprint(args.sql),
                violations=[v.model_dump() for v in pii_result.violations],
                error_code="pii_policy",
                question=original_question or None,
            )
            msg = "Query was rejected by the data-protection policy."
            raise PolicyRejectedError(msg)

        return await self._execute_structured(args, context, sql_result, pii_result, user, rid)

    async def _execute_structured(
        self,
        args: RunSqlToolArgs,
        context: ToolContext,
        sql_result: SqlPolicyResult,
        pii_result: PiiCheckResult,
        user: VaiUser,
        rid: str,
    ) -> StructuredSqlRun:
        groups = list(user.groups)

        sql_to_run = sql_result.rewritten_sql or args.sql

        profile_id = self._profile.meta.profile_id if self._profile else ""
        db_name = self._profile.meta.database_name if self._profile else ""

        def _exec() -> object:
            return self._runner.execute(
                sql_to_run,
                rewritten_sql=sql_result.rewritten_sql,
                audit_context={
                    "request_id": rid,
                    "user_id": str(user.id),
                    "user_email": user.email or "",
                    "user_groups": ",".join(groups),
                    "profile_id": profile_id,
                    "db_name": db_name,
                    "generated_sql": args.sql,
                },
            )

        try:
            qres = await asyncio.to_thread(_exec)
        except DbQueryTimeoutError as exc:
            emit_tool_audit(
                request_id=rid,
                user_id=user.id,
                access_groups=groups,
                tool_name="run_sql",
                decision="rejected",
                sql_hash=sql_fingerprint(args.sql),
                error_code="timeout",
            )
            raise SqlRunnerTimeoutError(exc.safe_message) from exc
        except RunnerError as exc:
            emit_tool_audit(
                request_id=rid,
                user_id=user.id,
                access_groups=groups,
                tool_name="run_sql",
                decision="rejected",
                sql_hash=sql_fingerprint(args.sql),
                error_code="runner",
            )
            raise QueryRejectedError(exc.safe_message) from exc

        emit_tool_audit(
            request_id=rid,
            user_id=user.id,
            access_groups=groups,
            tool_name="run_sql",
            decision="allowed",
            sql_hash=sql_fingerprint(sql_to_run),
            row_count=len(qres.rows),
            question=_question_from_tool_context(context) or None,
        )

        if not qres.columns:
            sql_ex = qres.sql_executed or sql_to_run
            return StructuredSqlRun(
                sql_executed=sql_ex,
                columns=[],
                rows=[],
                row_count=0,
                truncated=qres.truncated,
            )

        rows: list[dict[str, Any]] = [dict(r) for r in qres.rows]
        rows = enforce_min_group_size(
            rows,
            min_group_size=self._security_policy.min_group_size,
            user_groups=groups,
        )
        rows = apply_masking_rules(
            rows,
            masking_rules=self._security_policy.masking_rules,
            user_groups=groups,
        )
        cols = list(qres.columns)
        sql_ex = qres.sql_executed or sql_to_run

        if self._auto_learn_callback is not None and qres.row_count > 0:
            try:
                self._auto_learn_callback(
                    _question_from_tool_context(context),
                    sql_to_run,
                    qres.row_count,
                )
            except Exception:
                logger.warning("auto-learn callback failed", exc_info=True)

        return StructuredSqlRun(
            sql_executed=sql_ex,
            columns=cols,
            rows=rows,
            row_count=len(rows),
            truncated=qres.truncated,
        )

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext) -> pd.DataFrame:
        out = await self.run_sql_structured(args, context)
        if not out.columns:
            return pd.DataFrame()
        return pd.DataFrame(out.rows, columns=out.columns)
