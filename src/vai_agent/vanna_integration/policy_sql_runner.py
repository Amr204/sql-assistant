"""``SqlRunner`` that enforces ``SqlPolicyEngine`` / ``PiiPolicyEngine`` before ``MssqlRunner``."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import pandas as pd
from vanna.capabilities.sql_runner import SqlRunner
from vanna.capabilities.sql_runner.models import RunSqlToolArgs
from vanna.core.tool import ToolContext

from vai_agent.db.mssql_runner import MssqlRunner, QueryTimeoutError, RunnerError
from vai_agent.knowledge.profile_models import SecurityPolicy
from vai_agent.security.audit_log import emit_tool_audit, sql_fingerprint
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.result_policy import apply_masking_rules, enforce_min_group_size
from vai_agent.security.sql_policy import SqlPolicyEngine
from vai_agent.users import User as VaiUser

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._sql_policy = sql_policy
        self._pii_policy = pii_policy
        self._runner = runner
        self._security_policy = security_policy

    async def run_sql(self, args: RunSqlToolArgs, context: ToolContext) -> pd.DataFrame:
        user = _to_vai_user(context)
        groups = list(user.groups)
        rid = context.request_id

        def _validate_sql() -> tuple[object, object]:
            return (
                self._sql_policy.validate(args.sql, user_groups=groups),
                self._pii_policy.check(args.sql, user_groups=groups),
            )

        sql_result, pii_result = await asyncio.to_thread(_validate_sql)

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
            )
            msg = "Query was rejected by the SQL policy."
            raise PermissionError(msg)

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
            )
            msg = "Query was rejected by the data-protection policy."
            raise PermissionError(msg)

        sql_to_run = sql_result.rewritten_sql or args.sql

        def _exec() -> object:
            return self._runner.execute(sql_to_run, rewritten_sql=sql_result.rewritten_sql)

        try:
            qres = await asyncio.to_thread(_exec)
        except QueryTimeoutError as exc:
            emit_tool_audit(
                request_id=rid,
                user_id=user.id,
                access_groups=groups,
                tool_name="run_sql",
                decision="rejected",
                sql_hash=sql_fingerprint(args.sql),
                error_code="timeout",
            )
            raise PermissionError(exc.safe_message) from exc
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
            raise PermissionError(exc.safe_message) from exc

        emit_tool_audit(
            request_id=rid,
            user_id=user.id,
            access_groups=groups,
            tool_name="run_sql",
            decision="allowed",
            sql_hash=sql_fingerprint(sql_to_run),
            row_count=len(qres.rows),
        )

        if not qres.columns:
            return pd.DataFrame()

        rows: list[dict[str, object]] = list(qres.rows)
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
        return pd.DataFrame(rows, columns=qres.columns)
