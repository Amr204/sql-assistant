"""Guarded chat handler applies controls before delegating to the agent."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from vanna.core.user.request_context import RequestContext
from vanna.servers.base import ChatRequest

from tests.test_api_query import DummyEF
from vai_agent.api.rate_limit import RateLimitDecision, SlidingWindowRateLimiter
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime
from vai_agent.vanna_integration.guarded_chat import GuardedChatHandler

FIXTURE_ROOT = __import__("pathlib").Path(__file__).parent / "fixtures" / "profiles"


@pytest.mark.asyncio
async def test_guarded_handler_rejects_without_rate_limit_bypass(tmp_path, monkeypatch) -> None:
    profile = ProfileLoader(FIXTURE_ROOT).load("sample")
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst",
        llm_provider="none",
        chroma_persist_dir=str(tmp_path / "g"),
        _env_file=None,
    )
    mem, _ = create_memory(
        profile_id="sample",
        persist_dir=tmp_path / "g",
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

    handler = GuardedChatHandler(runtime.vanna, settings)
    req = ChatRequest(
        message="hello",
        request_context=RequestContext(metadata={"request_id": "rid1", "remote_ip": "127.0.0.1"}),
    )

    def fake_allow(self, *, user_id, ip, groups, settings):
        return RateLimitDecision(False, "blocked")

    monkeypatch.setattr(SlidingWindowRateLimiter, "allow_request", fake_allow)

    with pytest.raises(HTTPException) as ei:
        async for _ in handler.handle_stream(req):
            pass
    assert ei.value.status_code == 429
