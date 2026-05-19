"""Wrap existing synchronous profile tools as Vanna ``Tool`` implementations."""

from __future__ import annotations

import asyncio
import json
import logging

from vanna.core.tool import Tool, ToolContext, ToolResult

from vai_agent.knowledge.profile_models import Profile
from vai_agent.tools.explain_schema_tool import ExplainSchemaArgs, ExplainSchemaTool
from vai_agent.tools.profile_search_tool import ProfileSearchArgs, ProfileSearchTool
from vai_agent.users import User as VaiUser

logger = logging.getLogger(__name__)


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

        try:
            legacy = await asyncio.to_thread(_run)
            payload = json.dumps(legacy.data, ensure_ascii=False, default=str)
            return ToolResult(
                success=legacy.success,
                result_for_llm=payload if legacy.success else (legacy.error or "error"),
                ui_component=None,
                error=legacy.error,
                metadata=dict(legacy.metadata),
            )
        except Exception as exc:
            logger.error("ExplainSchemaTool failed: %s", exc, exc_info=True)
            return ToolResult(
                success=False,
                result_for_llm=f"Schema lookup failed: {type(exc).__name__}",
                result_for_user="تعذر استرجاع معلومات الجدول.",
                error=type(exc).__name__,
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

        try:
            legacy = await asyncio.to_thread(_run)
            payload = json.dumps(legacy.data, ensure_ascii=False, default=str)
            return ToolResult(
                success=legacy.success,
                result_for_llm=payload if legacy.success else (legacy.error or "error"),
                ui_component=None,
                error=legacy.error,
                metadata=dict(legacy.metadata),
            )
        except Exception as exc:
            logger.error("ProfileSearchTool failed: %s", exc, exc_info=True)
            return ToolResult(
                success=False,
                result_for_llm=f"Profile search failed: {type(exc).__name__}",
                result_for_user="تعذر البحث في ملف التعريف.",
                error=type(exc).__name__,
            )
