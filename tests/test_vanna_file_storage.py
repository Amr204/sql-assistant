"""Vanna RunSqlTool file sink stays under ``.data/vanna_files``."""

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

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


def test_vanna_file_storage_default_under_dot_data() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.vanna_file_storage_dir.startswith(".data/")
    assert "vanna_files" in s.vanna_file_storage_dir


@pytest.mark.asyncio
async def test_factory_uses_configured_vanna_file_root(tmp_path: Path) -> None:
    profile = ProfileLoader(FIXTURE_ROOT).load("sample")
    vfs = tmp_path / "vf"
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst",
        llm_provider="none",
        chroma_persist_dir=str(tmp_path / "ch"),
        vanna_file_storage_dir=str(vfs),
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
    build_vanna_runtime(
        profile=profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        vanna_embedding_function=DummyEF(),
    )
    assert vfs.is_dir()
