"""Wrap existing synchronous profile tools as Vanna ``Tool`` implementations."""

from __future__ import annotations

import asyncio
import json

from vanna.core.tool import Tool, ToolContext, ToolResult
from vanna.tools.run_sql import RunSqlTool

from vai_agent.knowledge.profile_models import Profile
from vai_agent.tools.explain_schema_tool import ExplainSchemaArgs, ExplainSchemaTool
from vai_agent.tools.profile_search_tool import ProfileSearchArgs, ProfileSearchTool
from vai_agent.users import User as VaiUser
from vai_agent.vanna_integration.policy_sql_runner import PolicySqlRunner


def _vai_user(ctx: ToolContext) -> VaiUser:
    u = ctx.user
    return VaiUser(id=u.id, email=u.email, groups=tuple(u.group_memberships))


class ExplainSchemaVannaTool(Tool[ExplainSchemaArgs]):
    def __init__(self, profile: Profile) -> None:
        self._tool = ExplainSchemaTool(profile)

    @property
    def name(self) -> str:
        return "explain_schema"

    @property
    def description(self) -> str:
        return self._tool.description

    def get_args_schema(self) -> type[ExplainSchemaArgs]:
        return ExplainSchemaArgs

    async def execute(self, context: ToolContext, args: ExplainSchemaArgs) -> ToolResult:
        def _run() -> object:
            return self._tool.execute(args, _vai_user(context))

        legacy = await asyncio.to_thread(_run)
        payload = json.dumps(legacy.data, ensure_ascii=False, default=str)
        return ToolResult(
            success=legacy.success,
            result_for_llm=payload if legacy.success else (legacy.error or "error"),
            ui_component=None,
            error=legacy.error,
            metadata=dict(legacy.metadata),
        )


class ProfileSearchVannaTool(Tool[ProfileSearchArgs]):
    def __init__(self, profile: Profile) -> None:
        self._tool = ProfileSearchTool(profile)

    @property
    def name(self) -> str:
        return "profile_search"

    @property
    def description(self) -> str:
        return self._tool.description

    def get_args_schema(self) -> type[ProfileSearchArgs]:
        return ProfileSearchArgs

    async def execute(self, context: ToolContext, args: ProfileSearchArgs) -> ToolResult:
        def _run() -> object:
            return self._tool.execute(args, _vai_user(context))

        legacy = await asyncio.to_thread(_run)
        payload = json.dumps(legacy.data, ensure_ascii=False, default=str)
        return ToolResult(
            success=legacy.success,
            result_for_llm=payload if legacy.success else (legacy.error or "error"),
            ui_component=None,
            error=legacy.error,
            metadata=dict(legacy.metadata),
        )


def build_policy_run_sql_tool(
    sql_runner: PolicySqlRunner,
    *,
    custom_tool_name: str = "run_sql",
    custom_tool_description: str | None = None,
) -> RunSqlTool:
    """Vanna :class:`~vanna.tools.run_sql.RunSqlTool` over :class:`PolicySqlRunner`."""

    desc = custom_tool_description or (
        "Execute safe read-only T-SQL SELECT queries. "
        "This tool enforces SQL policy, table/column allowlists, "
        "PII restrictions, row limits, timeouts, and audit logging. "
        "Never use it for INSERT, UPDATE, DELETE, DROP, ALTER, EXEC, or SELECT *."
    )
    return RunSqlTool(
        sql_runner,
        custom_tool_name=custom_tool_name,
        custom_tool_description=desc,
    )


def build_secure_run_sql_tool(sql_runner: PolicySqlRunner) -> RunSqlTool:
    """Build the legacy ``secure_run_sql`` tool name (alias of :func:`build_policy_run_sql_tool`)."""

    return build_policy_run_sql_tool(
        sql_runner,
        custom_tool_name="secure_run_sql",
        custom_tool_description=(
            "Alias for run_sql. Secure SELECT-only SQL execution against SQL Server."
        ),
    )
