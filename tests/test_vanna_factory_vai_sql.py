"""Vanna factory registers :class:`VaiRunSqlTool` (no stock CSV ``RunSqlTool``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from tests.test_api_query import DummyEF
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime
from vai_agent.vanna_integration.vai_run_sql_tool import VaiRunSqlTool

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


def _unwrap(tool: object) -> object:
    return getattr(tool, "_wrapped_tool", tool)


@pytest.mark.asyncio
async def test_factory_registers_vai_run_sql_tools(tmp_path: Path) -> None:
    profile = ProfileLoader(FIXTURE_ROOT).load("sample")
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst",
        llm_provider="none",
        chroma_persist_dir=str(tmp_path / "ch"),
        _env_file=None,
    )
    mem, _ = create_memory(
        profile_id="sample",
        persist_dir=tmp_path / "ch",
        embedding_function=DummyEF(),
    )
    cs = ConnectionSettings(
        _env_file=None,
        host="127.0.0.1",
        port=1433,
        database="db",
        username="u",
        password=SecretStr("pw"),
    )
    runtime = build_vanna_runtime(
        profile=profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        vanna_embedding_function=DummyEF(),
    )
    t_run = await runtime.vanna.tool_registry.get_tool("run_sql")
    assert isinstance(_unwrap(t_run), VaiRunSqlTool)
