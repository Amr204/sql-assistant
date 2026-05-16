"""Tests for the ``GET /health`` endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vai_agent.bootstrap import create_app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "sql-assistant"
    assert body["env"] in {"dev", "staging", "prod"}
    assert body["version"]


def test_health_response_schema_keys(client: TestClient) -> None:
    response = client.get("/health")
    body = response.json()
    assert set(body.keys()) == {"status", "app", "version", "env"}


def test_ready_returns_503_when_not_ready() -> None:
    app = create_app()
    app.state.readiness = {
        "ready": False,
        "profile_ready": True,
        "agent_ready": False,
        "memory_ready": True,
        "tools_ready": False,
        "llm_ready": False,
        "errors": ["agent init failed: missing DB env"],
    }
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_ready_returns_200_when_ready() -> None:
    app = create_app()
    app.state.readiness = {
        "ready": True,
        "profile_ready": True,
        "agent_ready": True,
        "memory_ready": True,
        "tools_ready": True,
        "llm_ready": False,
        "errors": [],
    }
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
