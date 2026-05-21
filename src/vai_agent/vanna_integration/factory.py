"""Construct a :class:`~vai_agent.vanna_integration.runtime.VaiVannaRuntime`."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import chromadb
from vanna.core.agent import Agent as VannaAgent
from vanna.core.registry import ToolRegistry
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SaveTextMemoryTool,
    SearchSavedCorrectToolUsesTool,
)

from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.db.mssql_runner import MssqlRunner
from vai_agent.knowledge.profile_models import Profile
from vai_agent.memory.chunking import ProfileChunk
from vai_agent.memory.memory_factory import AgentMemory, build_embedding_function
from vai_agent.memory.multi_search import MultiCollectionSearcher
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.sql_policy import SqlPolicyEngine
from vai_agent.users import User, UserResolver, UserResolverMode
from vai_agent.vai_app.context_enhancer import ContextEnhancer, ContextEnhancerConfig
from vai_agent.vanna_integration.enhanced_agent_memory import EnhancedChromaAgentMemory
from vai_agent.vanna_integration.model_llm import build_vanna_llm_service
from vai_agent.vanna_integration.policy_sql_runner import PolicySqlRunner
from vai_agent.vanna_integration.profile_llm_enhancer import ProfileLlmContextEnhancer
from vai_agent.vanna_integration.runtime import VaiVannaRuntime
from vai_agent.vanna_integration.user_resolver_bridge import LegacyUserResolverBridge
from vai_agent.vanna_integration.vai_run_sql_tool import VaiRunSqlTool
from vai_agent.vanna_integration.vanna_audit import JsonlVannaAuditLogger
from vai_agent.vanna_integration.vanna_tools import (
    ExplainSchemaVannaTool,
    ProfileSearchVannaTool,
)

logger = logging.getLogger(__name__)

_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_token(profile_id: str) -> str:
    s = _SAFE_RE.sub("_", profile_id.strip())
    return s[:60] if len(s) > 60 else s


def _vanna_collection_name(profile_id: str) -> str:
    return f"vanna_agent_{_safe_token(profile_id)}"


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


def _open_vanna_search_memory(
    chroma_client: chromadb.api.ClientAPI | None,
    profile_id: str,
) -> AgentMemory | None:
    if chroma_client is None:
        return None
    try:
        col = chroma_client.get_collection(_vanna_collection_name(profile_id))
        return AgentMemory(col)
    except Exception:
        return None


def _warm_vanna_agent_memory(agent_memory: EnhancedChromaAgentMemory) -> None:
    try:
        collection = agent_memory._get_collection()
        collection.query(query_texts=["__warmup__"], n_results=1)
        logger.info("vanna agent memory embedding warmed up")
    except Exception as exc:
        logger.warning(
            "vanna agent memory warmup failed (non-fatal)",
            extra={"error": str(exc)},
        )


def build_vanna_runtime(
    *,
    profile: Profile,
    connection_settings: ConnectionSettings,
    settings: Settings,
    chunk_memory: AgentMemory | None,
    chroma_client: chromadb.api.ClientAPI | None = None,
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
        profile=profile,
    )

    if vanna_embedding_function is None:
        vanna_embedding_function = build_embedding_function(
            embedding_device=settings.embedding_device,
        )

    agent_memory = EnhancedChromaAgentMemory(
        persist_directory=str(Path(settings.chroma_persist_dir).resolve()),
        collection_name=_vanna_collection_name(profile.meta.profile_id),
        embedding_function=vanna_embedding_function,
        profile_id=profile.meta.profile_id,
    )

    if settings.warmup_on_startup:
        _warm_vanna_agent_memory(agent_memory)

    memory_search: MultiCollectionSearcher | None = None
    if chunk_memory is not None:
        vanna_search = _open_vanna_search_memory(chroma_client, profile.meta.profile_id)
        memory_search = MultiCollectionSearcher(chunk_memory, vanna_search)

    # Vanna-native layer: VannaAgent, vanna.core.registry.ToolRegistry, memory tools.
    # VAI custom layer: PolicySqlRunner, VaiRunSqlTool, ProfileLlmContextEnhancer, JsonlVannaAuditLogger.
    audit = JsonlVannaAuditLogger()
    registry = ToolRegistry(audit_logger=audit)

    fb = ["analyst", "admin"]
    sql_groups = _tool_groups(profile, "run_sql", fb)
    schema_groups = _tool_groups(profile, "explain_schema", fb)
    search_groups = _tool_groups(profile, "profile_search", fb)

    registry.register_local_tool(
        VaiRunSqlTool(policy_runner, tool_name="run_sql"),
        sql_groups,
    )
    registry.register_local_tool(ExplainSchemaVannaTool(profile), schema_groups)
    registry.register_local_tool(ProfileSearchVannaTool(profile), search_groups)

    registry.register_local_tool(SearchSavedCorrectToolUsesTool(), ["analyst", "admin"])
    registry.register_local_tool(SaveQuestionToolArgsTool(), ["analyst", "admin"])
    registry.register_local_tool(SaveTextMemoryTool(), ["analyst", "admin"])

    for tool, groups in extra_local_tools or []:
        registry.register_local_tool(tool, groups)

    llm = build_vanna_llm_service(settings)
    enhancer_core = ContextEnhancer(
        profile,
        memory=memory_search,
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

    if chunk_memory is not None:
        def _auto_learn(question: str, sql: str, row_count: int) -> None:
            q = question.strip()
            if len(q) < 3:
                logger.debug("auto_learn skipped: question too short: %r", question)
                return
            chunk_id = hashlib.md5(
                f"{profile.meta.profile_id}:{question}:{sql}".encode(),
            ).hexdigest()[:16]
            chunk = ProfileChunk(
                document=f"Question: {question}\nSQL: {sql}",
                id=f"auto:{chunk_id}",
                metadata={
                    "kind": "auto_learned",
                    "question": question,
                    "sql": sql,
                    "row_count": row_count,
                    "profile_id": profile.meta.profile_id,
                },
            )
            chunk_memory.seed([chunk])

        policy_runner.set_auto_learn_callback(_auto_learn)

    return VaiVannaRuntime(
        vanna=agent,
        legacy_user_resolver=legacy_resolver,
        profile=profile,
        chunk_memory=chunk_memory,
        policy_runner=policy_runner,
    )
