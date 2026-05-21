"""Tests for Vanna runtime tool dispatch via :func:`build_vanna_runtime`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, SecretStr
from vanna.core.tool import Tool, ToolCall, ToolContext, ToolResult
from vanna.core.user.models import User

from tests.test_api_query import DummyEF, _AdminVannaTool
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


class _NoArgs(BaseModel):
    pass


class _BrokenVannaTool(Tool[_NoArgs]):
    @property
    def name(self) -> str:
        return "broken"

    @property
    def description(self) -> str:
        return "Always raises."

    def get_args_schema(self) -> type[_NoArgs]:
        return _NoArgs

    @property
    def access_groups(self) -> list[str]:
        return ["analyst"]

    async def execute(self, context: ToolContext, args: _NoArgs) -> ToolResult:
        raise RuntimeError("oops")


def _connection_settings() -> ConnectionSettings:
    return ConnectionSettings(
        _env_file=None,
        host="127.0.0.1",
        port=1433,
        database="db",
        username="u",
        password=SecretStr("pw"),
    )


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
    return build_vanna_runtime(
        profile=profile,
        connection_settings=_connection_settings(),
        settings=settings,
        chunk_memory=mem,
        extra_local_tools=extra_tools or [],
        vanna_embedding_function=DummyEF(),
    )


def _tool_context(runtime: object, *, user: User, request_id: str = "rid-1") -> ToolContext:
    return ToolContext(
        user=user,
        conversation_id="test",
        request_id=request_id,
        agent_memory=runtime.vanna.agent_memory,
        metadata={},
    )


@pytest.mark.asyncio
class TestRuntimeToolDispatch:
    async def test_unknown_tool(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        user = User(id="u", group_memberships=["analyst"])
        ctx = _tool_context(runtime, user=user)
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="rid-1", name="ghost", arguments={}),
            ctx,
        )
        assert not res.success
        assert res.error
        assert "not found" in res.error.lower()

    async def test_happy_path_explain_schema(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        user = User(id="u", group_memberships=["analyst"])
        ctx = _tool_context(runtime, user=user)
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="rid-1", name="explain_schema", arguments={}),
            ctx,
        )
        assert res.success
        assert res.result_for_llm

    async def test_request_id_in_metadata(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        user = User(id="u", group_memberships=["analyst"])
        ctx = _tool_context(runtime, user=user, request_id="explicit-rid")
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="explicit-rid", name="explain_schema", arguments={}),
            ctx,
        )
        assert res.success


@pytest.mark.asyncio
class TestArgValidation:
    async def test_invalid_args_returns_failure(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path)
        user = User(id="u", group_memberships=["analyst"])
        ctx = _tool_context(runtime, user=user)
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="rid-1", name="profile_search", arguments={"query": ""}),
            ctx,
        )
        assert not res.success
        assert res.error
        assert "invalid" in res.error.lower() or "argument" in res.error.lower()


@pytest.mark.asyncio
class TestAccess:
    async def test_user_without_group_is_denied(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path, extra_tools=[(_AdminVannaTool(), ["admin"])])
        user = User(id="u", group_memberships=["reader"])
        ctx = _tool_context(runtime, user=user)
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="rid-1", name="admin_only", arguments={}),
            ctx,
        )
        assert not res.success
        assert res.error
        assert "access" in res.error.lower()

    async def test_user_with_group_passes(self, tmp_path: Path) -> None:
        runtime = _build_runtime(tmp_path, extra_tools=[(_AdminVannaTool(), ["admin"])])
        user = User(id="u", group_memberships=["admin"])
        ctx = _tool_context(runtime, user=user)
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="rid-1", name="admin_only", arguments={}),
            ctx,
        )
        assert res.success


@pytest.mark.asyncio
class TestExceptionGuard:
    async def test_unhandled_tool_exception_returns_failure(self, tmp_path: Path) -> None:
        """Vanna ToolRegistry wraps tool exceptions in a failed ToolResult."""
        runtime = _build_runtime(tmp_path, extra_tools=[(_BrokenVannaTool(), ["analyst"])])
        user = User(id="u", group_memberships=["analyst"])
        ctx = _tool_context(runtime, user=user)
        res = await runtime.vanna.tool_registry.execute(
            ToolCall(id="rid-1", name="broken", arguments={}),
            ctx,
        )
        assert not res.success
        assert res.error
        assert "Execution failed" in res.error
