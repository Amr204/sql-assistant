"""Tests for the ``/agent/*`` HTTP endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from vai_agent.bootstrap import create_app
from vai_agent.config.settings import get_settings
from vai_agent.knowledge import ProfileLoader
from vai_agent.tools.base import ToolBase, ToolResult
from vai_agent.tools.explain_schema_tool import ExplainSchemaTool
from vai_agent.tools.profile_search_tool import ProfileSearchTool
from vai_agent.users import User, UserResolver, UserResolverMode
from vai_agent.vai_app.agent_factory import Agent
from vai_agent.vai_app.tool_registry import ToolRegistry

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


class _NoArgs(BaseModel):
    pass


class _AdminTool(ToolBase):
    name = "admin_only"
    description = "Restricted."
    args_model = _NoArgs
    access_groups = ("admin",)

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        return self._ok({"ok": True})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture()
def dev_agent(sample_profile) -> Agent:
    """An Agent wired with read-only tools and a dev user resolver."""
    registry = ToolRegistry()
    registry.register_all([
        ExplainSchemaTool(sample_profile),
        ProfileSearchTool(sample_profile),
        _AdminTool(),
    ])
    resolver = UserResolver(
        UserResolverMode.dev,
        default_user=User(id="dev", groups=("analyst",)),
    )
    return Agent(registry, resolver)


@pytest.fixture()
def client_with_agent(dev_agent: Agent) -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    app.state.agent = dev_agent
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture()
def client_no_agent() -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    # No agent attached — endpoints must return 503.
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 503 when no agent
# ---------------------------------------------------------------------------


class TestServiceUnavailable:
    def test_list_tools_returns_503(self, client_no_agent: TestClient) -> None:
        r = client_no_agent.get("/agent/tools")
        assert r.status_code == 503

    def test_invoke_returns_503(self, client_no_agent: TestClient) -> None:
        r = client_no_agent.post("/agent/tools/x/invoke", json={"args": {}})
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# List tools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_lists_tools_for_dev_user(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.get("/agent/tools")
        assert r.status_code == 200
        body = r.json()
        names = {t["name"] for t in body["tools"]}
        # Dev user is in 'analyst' group → no access to 'admin_only'
        assert names == {"explain_schema", "profile_search"}

    def test_each_tool_has_schema(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.get("/agent/tools")
        body = r.json()
        for tool in body["tools"]:
            assert tool["args_schema"]  # JSON schema dict
            assert "name" in tool and "description" in tool


# ---------------------------------------------------------------------------
# Invoke
# ---------------------------------------------------------------------------


class TestInvoke:
    def test_explain_schema_lists_tables(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/explain_schema/invoke", json={"args": {}},
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
        self, client_with_agent: TestClient,
    ) -> None:
        r = client_with_agent.post(
            "/agent/tools/ghost/invoke", json={"args": {}},
        )
        # The tool dispatcher returns a ToolResult, not an HTTP error.
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "Unknown tool" in body["error"]

    def test_invalid_args_returns_failure(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/profile_search/invoke",
            json={"args": {"query": ""}},  # min_length=1 violated
        )
        assert r.status_code == 200
        body = r.json()
        assert not body["success"]
        assert "Invalid arguments" in body["error"]

    def test_invoke_admin_only_tool_denied(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/admin_only/invoke", json={"args": {}},
        )
        body = r.json()
        assert not body["success"]
        assert "Access denied" in body["error"]

    def test_request_id_in_response_metadata(self, client_with_agent: TestClient) -> None:
        r = client_with_agent.post(
            "/agent/tools/explain_schema/invoke", json={"args": {}},
        )
        body = r.json()
        assert "request_id" in body["metadata"]


# ---------------------------------------------------------------------------
# Header-mode user resolution
# ---------------------------------------------------------------------------


@pytest.fixture()
def header_agent(sample_profile) -> Agent:
    registry = ToolRegistry()
    registry.register_all([
        ExplainSchemaTool(sample_profile),
        _AdminTool(),
    ])
    return Agent(registry, UserResolver(UserResolverMode.header))


@pytest.fixture()
def client_header_mode(header_agent: Agent) -> Iterator[TestClient]:
    get_settings.cache_clear()
    app = create_app()
    app.state.agent = header_agent
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
        # 'admin' group was NOT requested → admin_only is excluded
        assert names == {"explain_schema"}

    def test_admin_group_from_header_is_stripped(self, client_header_mode: TestClient) -> None:
        # User claims admin, but the resolver strips it. So admin_only is hidden.
        r = client_header_mode.get(
            "/agent/tools",
            headers={"X-User-Id": "evil", "X-User-Groups": "admin,analyst"},
        )
        names = {t["name"] for t in r.json()["tools"]}
        assert "admin_only" not in names
