"""Tests for :class:`vanna.core.registry.ToolRegistry` wired by ``build_vanna_runtime``."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr
from vanna.core.user.models import User

from tests.test_api_query import DummyEF, _AdminVannaTool
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime
from vai_agent.vanna_integration.vai_run_sql_tool import VaiRunSqlTool

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"

_CORE_TOOLS = frozenset({
    "run_sql",
    "explain_schema",
    "profile_search",
    "save_question_tool_args",
    "save_text_memory",
    "search_saved_correct_tool_uses",
})


def _build_runtime(tmp_path: Path, *, extra_tools: list | None = None):
    profile = ProfileLoader(FIXTURE_ROOT).load("sample")
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst,admin",
        llm_provider="none",
        chroma_persist_dir=str(tmp_path / "c"),
        _env_file=None,
    )
    mem, _ = create_memory(
        profile_id="sample",
        persist_dir=tmp_path / "c",
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
    return build_vanna_runtime(
        profile=profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        extra_local_tools=extra_tools or [],
        vanna_embedding_function=DummyEF(),
    )


@pytest.mark.asyncio
class TestFactoryToolRegistry:
    async def test_registers_core_tools(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        user = User(id="u", group_memberships=["analyst"])
        schemas = await runtime.vanna.tool_registry.get_schemas(user)
        names = {s.name for s in schemas}
        assert _CORE_TOOLS <= names

    async def test_get_tool_run_sql(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        tool = await runtime.vanna.tool_registry.get_tool("run_sql")
        inner = getattr(tool, "_wrapped_tool", tool)
        assert isinstance(inner, VaiRunSqlTool)

    async def test_analyst_sees_open_tools_only(self, tmp_path: Path) -> None:
        runtime = _build_runtime(
            tmp_path,
            extra_tools=[(_AdminVannaTool(), ["admin"])],
        )
        user = User(id="u", group_memberships=["analyst"])
        schemas = await runtime.vanna.tool_registry.get_schemas(user)
        names = {s.name for s in schemas}
        assert "admin_only" not in names
        assert "run_sql" in names
        assert "explain_schema" in names

    async def test_admin_sees_restricted_tool(self, tmp_path: Path) -> None:
        runtime = _build_runtime(
            tmp_path,
            extra_tools=[(_AdminVannaTool(), ["admin"])],
        )
        user = User(id="u", group_memberships=["admin"])
        schemas = await runtime.vanna.tool_registry.get_schemas(user)
        names = {s.name for s in schemas}
        assert "admin_only" in names

    async def test_access_groups_are_non_empty_for_run_sql(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        user = User(id="u", group_memberships=["analyst"])
        schemas = await runtime.vanna.tool_registry.get_schemas(user)
        run_sql = next(s for s in schemas if s.name == "run_sql")
        assert run_sql.access_groups
        assert set(run_sql.access_groups) & {"analyst", "admin"}
