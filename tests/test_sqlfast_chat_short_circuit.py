"""SQL fast path returns before GuardedChatHandler when service succeeds."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tests.test_api_query import DummyEF
from vai_agent.api.v1 import router as api_v1_router
from vai_agent.api.v1.schemas import ChatResponse
from vai_agent.config.settings import Settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.sqlfast.service import SqlFastOutcome, SqlFastResult, SqlFastService
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
        sql_fast_path_enabled=True,
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
    app.state.readiness = {"ready": True, "errors": []}
    return app


@pytest.mark.asyncio
async def test_sql_fast_success_skips_guarded_handler(v1_chat_app, monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"vanna": False}

    async def fake_run(self, *, question: str, v_user, conversation_id, request_id):
        return SqlFastResult(
            SqlFastOutcome.SUCCESS,
            ChatResponse(
                conversation_id=conversation_id,
                request_id=request_id,
                question=question,
                answer="mock answer",
                sql="SELECT COUNT(*) AS [record_count] FROM dbo.Customers",
                explanation=None,
                confidence=1.0,
                table=None,
                warnings=[],
                errors=[],
                execution_ms=1,
                path="sql_fast",
                timings={"context_ms": 1, "llm_ms": 1, "sql_ms": 1, "present_ms": 0},
            ),
            {"context_ms": 1, "llm_ms": 1, "sql_ms": 1, "present_ms": 0},
        )

    async def fail_vanna(self, request):
        called["vanna"] = True
        raise AssertionError("GuardedChatHandler should not run")

    monkeypatch.setattr(SqlFastService, "run", fake_run)
    monkeypatch.setattr(
        "vai_agent.vanna_integration.guarded_chat.GuardedChatHandler.handle_poll",
        fail_vanna,
    )

    transport = ASGITransport(app=v1_chat_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat",
            json={"question": "How many customers in Spain?"},
        )

    assert resp.status_code == 200
    assert called["vanna"] is False
    data = resp.json()
    assert data["path"] == "sql_fast"
    assert data["answer"] == "mock answer"
    assert "timings" in data and data["timings"].get("total_ms") is not None
