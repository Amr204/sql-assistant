"""Persist successful SQL fast-path Q/A into Vanna Chroma agent memory (no admin tool)."""

from __future__ import annotations

import logging

from vanna.core.tool.models import ToolContext
from vanna.core.user.models import User as VannaUser

from vai_agent.config.settings import Settings
from vai_agent.vanna_integration.runtime import VaiVannaRuntime

logger = logging.getLogger(__name__)


async def save_fast_path_memory(
    *,
    runtime: VaiVannaRuntime,
    settings: Settings,
    question: str,
    sql: str,
    profile_id: str,
    row_count: int,
    v_user: VannaUser,
    conversation_id: str | None,
    request_id: str,
) -> None:
    """Call :meth:`~vanna.integrations.chromadb.ChromaAgentMemory.save_tool_usage` for learning."""

    if not settings.agent_memory_auto_save:
        return

    mem = runtime.vanna.agent_memory
    ctx = ToolContext(
        user=v_user,
        conversation_id=conversation_id or "",
        request_id=request_id,
        agent_memory=mem,
        metadata={"source": "sql_fast_path"},
    )
    try:
        await mem.save_tool_usage(
            question=question,
            tool_name="run_sql",
            args={"sql": sql},
            context=ctx,
            success=True,
            metadata={
                "profile_id": profile_id,
                "row_count": row_count,
                "source": "sql_fast_path",
            },
        )
    except Exception:
        logger.warning("sql fast path memory save failed", exc_info=True)
