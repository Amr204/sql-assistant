"""Legacy synchronous tool dispatcher (unit-test compatibility).

**Production runtime** uses ``vanna.core.agent.Agent`` built in
:mod:`vai_agent.vanna_integration.factory` — not this class.  Keep
:class:`Agent` / :func:`build_agent` for tests and offline tool tests;
do not wire this module as the primary HTTP stack.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from vai_agent.db.connection import ConnectionSettings
from vai_agent.db.mssql_runner import MssqlRunner
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.sql_policy import SqlPolicyEngine
from vai_agent.tools import (
    ExplainSchemaTool,
    ProfileSearchTool,
    SecureRunSqlTool,
    ToolResult,
)
from vai_agent.users import UserResolver
from vai_agent.vai_app.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from vai_agent.knowledge.profile_models import Profile
    from vai_agent.users import User

logger = logging.getLogger(__name__)


class Agent:
    """Tool-dispatching orchestrator. Synchronous; thread-safe to read."""

    def __init__(
        self,
        registry: ToolRegistry,
        user_resolver: UserResolver,
    ) -> None:
        self.registry = registry
        self.user_resolver = user_resolver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        user: User,
        *,
        request_id: str | None = None,
    ) -> ToolResult:
        """Run *tool_name* on behalf of *user*.

        Returns a :class:`ToolResult` — never raises for user-controllable
        errors (unknown tool, invalid args, access denied, downstream
        failure). The result's ``metadata['request_id']`` is always set.
        """
        request_id = request_id or uuid.uuid4().hex
        log_extra = {
            "request_id": request_id,
            "tool": tool_name,
            "user_id": user.id,
        }

        tool = self.registry.get(tool_name)
        if tool is None:
            logger.info("unknown tool requested", extra=log_extra)
            return ToolResult(
                success=False,
                tool=tool_name,
                error=f"Unknown tool: {tool_name!r}.",
                metadata={"request_id": request_id},
            )

        if not self.registry.user_can_use(tool, user):
            logger.warning("access denied", extra=log_extra)
            return ToolResult(
                success=False,
                tool=tool_name,
                error="Access denied for this tool.",
                metadata={"request_id": request_id},
            )

        try:
            validated_args = tool.args_model.model_validate(args)
        except ValidationError as exc:
            logger.info("invalid tool args", extra={**log_extra, "errors": exc.errors()})
            return ToolResult(
                success=False,
                tool=tool_name,
                error="Invalid arguments for tool.",
                metadata={
                    "request_id": request_id,
                    "validation_errors": [
                        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                        for e in exc.errors()
                    ],
                },
            )

        logger.info("invoking tool", extra=log_extra)
        try:
            result = tool.execute(validated_args, user)
        except Exception as exc:
            # Tools are expected to return ToolResult on all known failure
            # modes; an unhandled exception here is a bug. Log type/name
            # only — never the message (may contain DB internals).
            logger.exception(
                "tool raised unexpectedly",
                extra={**log_extra, "exc_type": type(exc).__name__},
            )
            return ToolResult(
                success=False,
                tool=tool_name,
                error="Internal error while running the tool.",
                metadata={"request_id": request_id, "exc_type": type(exc).__name__},
            )

        # Merge in the request_id without dropping any metadata the tool
        # already set.
        merged_metadata = dict(result.metadata)
        merged_metadata.setdefault("request_id", request_id)
        return result.model_copy(update={"metadata": merged_metadata})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_agent(
    *,
    profile: Profile,
    connection_settings: ConnectionSettings,
    user_resolver: UserResolver,
    max_rows: int | None = None,
    query_timeout: int | None = None,
) -> Agent:
    """Wire together the Phase-6 agent stack.

    Parameters
    ----------
    profile:
        Loaded :class:`Profile`. Supplies the security policy used by
        both engines and the schema/knowledge for the explainer + search
        tools.
    connection_settings:
        Database connection details for :class:`MssqlRunner`.
    user_resolver:
        Pre-built resolver. The factory does not assume a particular
        mode so tests and the FastAPI layer can inject the right one.
    max_rows / query_timeout:
        Optional overrides; otherwise taken from
        ``profile.security_policy``.
    """
    security_policy = profile.security_policy
    sql_engine = SqlPolicyEngine(security_policy)
    pii_engine = PiiPolicyEngine(security_policy)
    runner = MssqlRunner(
        connection_settings,
        max_rows=max_rows or security_policy.max_rows,
        query_timeout=query_timeout or security_policy.max_execution_seconds,
    )

    registry = ToolRegistry()
    registry.register_all([
        SecureRunSqlTool(sql_engine, pii_engine, runner),
        ExplainSchemaTool(profile),
        ProfileSearchTool(profile),
    ])

    return Agent(registry, user_resolver)
