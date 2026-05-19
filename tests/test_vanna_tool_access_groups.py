"""Vanna ``ToolRegistry`` access groups for SQL tools (``run_sql`` primary, alias optional)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from tests.test_api_query import DummyEF
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime

FIXTURE_ROOT = __import__("pathlib").Path(__file__).parent / "fixtures" / "profiles"


@pytest.mark.asyncio
async def test_run_sql_has_non_empty_access_groups(tmp_path) -> None:
    profile = ProfileLoader(FIXTURE_ROOT).load("sample")
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst",
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
    runtime = build_vanna_runtime(
        profile=profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        vanna_embedding_function=DummyEF(),
    )

    from vanna.core.user.models import User

    user = User(id="u", group_memberships=["analyst"])
    schemas = await runtime.vanna.tool_registry.get_schemas(user)
    names = {s.name for s in schemas}
    assert "run_sql" in names

    run_sql = next(t for t in schemas if t.name == "run_sql")
    assert run_sql.access_groups
    assert set(run_sql.access_groups) & {"analyst", "admin"}
