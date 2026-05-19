"""``/api/v1/chat`` uses :class:`~vai_agent.vanna_integration.guarded_chat.GuardedChatHandler`."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tests.test_api_query import DummyEF
from vai_agent.api.v1 import router as api_v1_router
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture()
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture()
def v1_chat_app(sample_profile, tmp_path):
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
        profile=sample_profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        vanna_embedding_function=DummyEF(),
    )
    app = FastAPI()
    app.include_router(api_v1_router)
    app.state.agent = runtime
    app.state.readiness = {
        "ready": True,
        "profile_ready": True,
        "agent_ready": True,
        "memory_ready": True,
        "tools_ready": True,
        "llm_ready": False,
        "errors": [],
    }
    return app


def test_api_v1_chat_503_when_agent_missing() -> None:
    app = FastAPI()
    app.include_router(api_v1_router)
    app.state.agent = None
    app.state.readiness = {"ready": False, "errors": ["no agent"]}
    with TestClient(app) as client:
        r = client.post("/api/v1/chat", json={"question": "hello"})
    assert r.status_code == 503
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("code") == "AGENT_NOT_READY"


@pytest.mark.asyncio
async def test_api_v1_chat_uses_guarded_handler(v1_chat_app, monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"handle_poll": False}

    async def fake_handle_poll(self, request):
        called["handle_poll"] = True
        from vanna.servers.base import ChatResponse, ChatStreamChunk

        return ChatResponse(
            chunks=[
                ChatStreamChunk(
                    rich={},
                    simple={"text": "ok"},
                    conversation_id="c1",
                    request_id="r1",
                ),
            ],
            conversation_id="c1",
            request_id="r1",
            total_chunks=1,
        )

    monkeypatch.setattr(
        "vai_agent.vanna_integration.guarded_chat.GuardedChatHandler.handle_poll",
        fake_handle_poll,
    )

    transport = ASGITransport(app=v1_chat_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/chat", json={"question": "hello"})

    assert resp.status_code == 200
    assert called["handle_poll"] is True
    data = resp.json()
    assert data["request_id"] == "r1"
    assert data["question"] == "hello"
    assert "answer" in data
    assert "sql" in data
    assert "table" in data
    assert "explanation" in data
    assert "execution_ms" in data
    assert "warnings" in data
    assert "confidence" in data
    assert "errors" in data
    assert isinstance(data["errors"], list)
    assert "raw" not in data
    assert "tables" not in data
