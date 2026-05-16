"""``/chat`` must delegate to Vanna :class:`~vanna.servers.base.chat_handler.ChatHandler`."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tests.test_api_query import DummyEF
from vai_agent.api.chat import router as chat_router
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
def chat_only_app(sample_profile, tmp_path):
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
    app.include_router(chat_router)
    app.state.agent = runtime
    return app


@pytest.mark.asyncio
async def test_chat_uses_chat_handler_handle_poll(chat_only_app, monkeypatch: pytest.MonkeyPatch) -> None:
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
        "vanna.servers.base.chat_handler.ChatHandler.handle_poll",
        fake_handle_poll,
    )

    transport = ASGITransport(app=chat_only_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/chat", json={"question": "hello"})

    assert resp.status_code == 200
    assert called["handle_poll"] is True
    data = resp.json()
    assert data["request_id"] == "r1"
    assert data["result"]["conversation_id"] == "c1"
    assert data["result"]["chunks"]
