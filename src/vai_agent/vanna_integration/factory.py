"""Construct a :class:`~vai_agent.vanna_integration.runtime.VaiVannaRuntime`."""

from __future__ import annotations

import re
from pathlib import Path

from vanna.core.agent import Agent as VannaAgent
from vanna.core.registry import ToolRegistry
from vanna.integrations.chromadb import ChromaAgentMemory
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SaveTextMemoryTool,
    SearchSavedCorrectToolUsesTool,
)

from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.db.mssql_runner import MssqlRunner
from vai_agent.knowledge.profile_models import Profile
from vai_agent.memory.memory_factory import AgentMemory
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.sql_policy import SqlPolicyEngine
from vai_agent.users import User, UserResolver, UserResolverMode
from vai_agent.vai_app.context_enhancer import ContextEnhancer, ContextEnhancerConfig
from vai_agent.vanna_integration.openrouter_llm import build_vanna_llm_service
from vai_agent.vanna_integration.policy_sql_runner import PolicySqlRunner
from vai_agent.vanna_integration.profile_llm_enhancer import ProfileLlmContextEnhancer
from vai_agent.vanna_integration.runtime import VaiVannaRuntime
from vai_agent.vanna_integration.user_resolver_bridge import LegacyUserResolverBridge
from vai_agent.vanna_integration.vanna_audit import JsonlVannaAuditLogger
from vai_agent.vanna_integration.vanna_tools import (
    ExplainSchemaVannaTool,
    ProfileSearchVannaTool,
    build_policy_run_sql_tool,
)

_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_token(profile_id: str) -> str:
    s = _SAFE_RE.sub("_", profile_id.strip())
    return s[:60] if len(s) > 60 else s


def _parse_dev_groups(raw: str) -> tuple[str, ...]:
    return tuple(g.strip() for g in raw.split(",") if g.strip())


def _build_legacy_user_resolver(settings: Settings) -> UserResolver:
    if settings.user_resolver_mode == "dev":
        return UserResolver(
            UserResolverMode.dev,
            default_user=User(
                id=settings.dev_user_id,
                email=settings.dev_user_email,
                groups=_parse_dev_groups(settings.dev_user_groups),
            ),
        )
    return UserResolver(settings.user_resolver_mode)


def _tool_groups(profile: Profile, tool_name: str, fallback: list[str]) -> list[str]:
    """Resolve Vanna ``access_groups`` for *tool_name* from ``security_policy``."""

    policy = profile.security_policy
    raw_map = policy.tool_access_groups
    if isinstance(raw_map, dict):
        value = raw_map.get(tool_name)
        if isinstance(value, list) and value:
            return [str(v).strip() for v in value if str(v).strip()]

    raw = getattr(policy, "user_access_groups", None)
    if isinstance(raw, dict):
        value = raw.get(tool_name)
        if isinstance(value, list) and value:
            return [str(v).strip() for v in value if str(v).strip()]

    names = [g.name.strip() for g in policy.user_access_groups if g.name.strip()]
    if names:
        return list(dict.fromkeys(names))

    return list(dict.fromkeys(fallback))


def build_vanna_runtime(
    *,
    profile: Profile,
    connection_settings: ConnectionSettings,
    settings: Settings,
    chunk_memory: AgentMemory | None,
    extra_local_tools: list[tuple[object, list[str]]] | None = None,
    vanna_embedding_function: object | None = None,
) -> VaiVannaRuntime:
    """Wire Vanna ``Agent`` with policy-gated SQL and profile tools."""

    legacy_resolver = _build_legacy_user_resolver(settings)
    user_resolver = LegacyUserResolverBridge(legacy_resolver)

    security_policy = profile.security_policy
    sql_engine = SqlPolicyEngine(security_policy)
    pii_engine = PiiPolicyEngine(security_policy)
    runner = MssqlRunner(
        connection_settings,
        max_rows=security_policy.max_rows,
        query_timeout=security_policy.max_execution_seconds,
    )
    policy_runner = PolicySqlRunner(
        sql_engine,
        pii_engine,
        runner,
        security_policy=security_policy,
    )

    agent_memory = ChromaAgentMemory(
        persist_directory=str(Path(settings.chroma_persist_dir).resolve()),
        collection_name=f"vanna_agent_{_safe_token(profile.meta.profile_id)}",
        embedding_function=vanna_embedding_function,
    )

    audit = JsonlVannaAuditLogger()
    registry = ToolRegistry(audit_logger=audit)

    fb = ["analyst", "admin"]
    sql_groups = _tool_groups(profile, "run_sql", fb)
    schema_groups = _tool_groups(profile, "explain_schema", fb)
    search_groups = _tool_groups(profile, "profile_search", fb)
    secure_alias_groups = _tool_groups(profile, "secure_run_sql", sql_groups)

    registry.register_local_tool(
        build_policy_run_sql_tool(policy_runner, custom_tool_name="run_sql"),
        sql_groups,
    )
    registry.register_local_tool(
        build_policy_run_sql_tool(
            policy_runner,
            custom_tool_name="secure_run_sql",
            custom_tool_description="Alias for run_sql. Secure SELECT-only SQL execution.",
        ),
        secure_alias_groups,
    )
    registry.register_local_tool(ExplainSchemaVannaTool(profile), schema_groups)
    registry.register_local_tool(ProfileSearchVannaTool(profile), search_groups)

    registry.register_local_tool(SearchSavedCorrectToolUsesTool(), ["analyst", "admin"])
    registry.register_local_tool(SaveQuestionToolArgsTool(), ["admin"])
    registry.register_local_tool(SaveTextMemoryTool(), ["admin"])

    for tool, groups in extra_local_tools or []:
        registry.register_local_tool(tool, groups)

    llm = build_vanna_llm_service(settings)
    enhancer_core = ContextEnhancer(
        profile,
        memory=chunk_memory,
        config=ContextEnhancerConfig(max_tokens=settings.context_max_tokens),
    )
    llm_enhancer = ProfileLlmContextEnhancer(enhancer_core)

    agent = VannaAgent(
        llm_service=llm,
        tool_registry=registry,
        user_resolver=user_resolver,
        agent_memory=agent_memory,
        llm_context_enhancer=llm_enhancer,
        audit_logger=audit,
    )
    return VaiVannaRuntime(
        vanna=agent,
        legacy_user_resolver=legacy_resolver,
        profile=profile,
        chunk_memory=chunk_memory,
    )
