"""Tests for the ``/agent/*`` HTTP endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from vanna.core.tool import Tool, ToolContext, ToolResult

from vai_agent.bootstrap import create_app
from vai_agent.config.settings import Settings, get_settings
from vai_agent.db.connection import ConnectionSettings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.memory_factory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


class DummyEF:
    """Lightweight Chroma embedding function for tests."""

    def __init__(self) -> None:
        pass

    def name(self) -> str:
        return "dummy_ef"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    @staticmethod
    def _embed(texts: list[str]) -> list[list[float]]:
        return [[float(hash(t) % 100) / 100.0, 0.5, 0.5] for t in texts]


class _NoArgs(BaseModel):
    pass


class _AdminVannaTool(Tool[_NoArgs]):
    @property
    def name(self) -> str:
        return "admin_only"

    @property
    def description(self) -> str:
        return "Restricted."

    def get_args_schema(self) -> type[_NoArgs]:
        return _NoArgs

    @property
    def access_groups(self) -> list[str]:
        return ["admin"]

    async def execute(self, context: ToolContext, args: _NoArgs) -> ToolResult:
        return ToolResult(
            success=True,
            result_for_llm="{}",
            ui_component=None,
            error=None,
            metadata={},
        )


@pytest.fixture()
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture()
def dev_runtime(sample_profile, tmp_path):
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="dev",
        dev_user_id="dev",
        dev_user_groups="analyst",
        llm_provider="none",
        chroma_persist_dir=str(tmp_path / "c1"),
        _env_file=None,
    )
    mem, _ = create_memory(
        profile_id="sample",
        persist_dir=tmp_path / "c1",
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
        profile=sample_profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        extra_local_tools=[(_AdminVannaTool(), ["admin"])],
        vanna_embedding_function=DummyEF(),
    )


@pytest.fixture()
def client_with_agent(dev_runtime) -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    app.state.agent = dev_runtime
    app.state.readiness.update(
        {
            "ready": True,
            "profile_ready": True,
            "agent_ready": True,
            "memory_ready": True,
            "tools_ready": True,
            "llm_ready": False,
            "errors": [],
        },
    )
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture()
def client_no_agent() -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    app.state.agent = None
    app.state.readiness = {
        "ready": False,
        "profile_ready": bool(getattr(app.state, "profile", None)),
        "agent_ready": False,
        "memory_ready": bool(getattr(app.state, "memory", None)),
        "tools_ready": False,
        "llm_ready": False,
        "errors": ["agent disabled by test fixture"],
    }
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


class TestServiceUnavailable:
    def test_list_tools_returns_503(self, client_no_agent: TestClient) -> None:
        r = client_no_agent.get("/agent/tools")
        assert r.status_code == 503

    def test_invoke_returns_503(self, client_no_agent: TestClient) -> None:
        r = client_no_agent.post("/agent/tools/x/invoke", json={"args": {}})
        assert r.status_code == 503


class TestListTools:
    def test_lists_tools_for_dev_user(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.get("/agent/tools")
        assert r.status_code == 200
        body = r.json()
        names = {t["name"] for t in body["tools"]}
        assert names == {
            "explain_schema",
            "profile_search",
            "run_sql",
            "secure_run_sql",
            "search_saved_correct_tool_uses",
        }

    def test_each_tool_has_schema(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.get("/agent/tools")
        body = r.json()
        for tool in body["tools"]:
            assert tool["args_schema"]
            assert "name" in tool and "description" in tool


class TestInvoke:
    def test_explain_schema_lists_tables(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/explain_schema/invoke",
            json={"args": {}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"]
        assert body["tool"] == "explain_schema"
        names = [t["name"] for t in body["data"]["tables"]]
        assert "Customers" in names

    def test_explain_schema_for_specific_table(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/explain_schema/invoke",
            json={"args": {"table": "Customers"}},
        )
        body = r.json()
        assert body["success"]
        assert body["data"]["primary_key"] == ["CustomerID"]

    def test_profile_search(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/profile_search/invoke",
            json={"args": {"query": "customer"}},
        )
        body = r.json()
        assert body["success"]
        assert body["data"]["total_hits"] > 0

    def test_invoke_unknown_tool_returns_200_with_failure(
        self,
        client_with_agent: TestClient,
    ) -> None:
        r = client_with_agent.post(
            "/agent/tools/ghost/invoke",
            json={"args": {}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "not found" in (body["error"] or "").lower()

    def test_invalid_args_returns_failure(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/profile_search/invoke",
            json={"args": {"query": ""}},
        )
        assert r.status_code == 200
        body = r.json()
        assert not body["success"]
        assert "Invalid arguments" in body["error"]

    def test_invoke_admin_only_tool_denied(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/admin_only/invoke",
            json={"args": {}},
        )
        body = r.json()
        assert not body["success"]
        assert "access" in (body["error"] or "").lower()

    def test_request_id_in_response_metadata(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/explain_schema/invoke",
            json={"args": {}},
        )
        body = r.json()
        assert "request_id" in body["metadata"]


@pytest.fixture()
def header_runtime(sample_profile, tmp_path):
    settings = Settings(  # type: ignore[call-arg]
        db_profile_id="sample",
        profiles_root=str(FIXTURE_ROOT),
        user_resolver_mode="header",
        chroma_persist_dir=str(tmp_path / "c2"),
        _env_file=None,
    )
    mem, _ = create_memory(
        profile_id="sample",
        persist_dir=tmp_path / "c2",
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
        profile=sample_profile,
        connection_settings=cs,
        settings=settings,
        chunk_memory=mem,
        extra_local_tools=[(_AdminVannaTool(), ["admin"])],
        vanna_embedding_function=DummyEF(),
    )


@pytest.fixture()
def client_header_mode(header_runtime) -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    app.state.agent = header_runtime
    app.state.readiness.update(
        {
            "ready": True,
            "profile_ready": True,
            "agent_ready": True,
            "memory_ready": True,
            "tools_ready": True,
            "llm_ready": False,
            "errors": [],
        },
    )
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


class TestHeaderModeResolution:
    def test_missing_user_header_returns_401(self, client_header_mode: TestClient) -> None:
        r = client_header_mode.get("/agent/tools")
        assert r.status_code == 401

    def test_with_user_header_returns_200(self, client_header_mode: TestClient) -> None:
        r = client_header_mode.get(
            "/agent/tools",
            headers={"X-User-Id": "alice", "X-User-Groups": "analyst"},
        )
        assert r.status_code == 200
        names = {t["name"] for t in r.json()["tools"]}
        assert names == {
            "explain_schema",
            "profile_search",
            "run_sql",
            "secure_run_sql",
            "search_saved_correct_tool_uses",
        }

    def test_admin_group_from_header_is_stripped(self, client_header_mode: TestClient) -> None:
        r = client_header_mode.get(
            "/agent/tools",
            headers={"X-User-Id": "evil", "X-User-Groups": "admin,analyst"},
        )
        names = {t["name"] for t in r.json()["tools"]}
        assert "admin_only" not in names
