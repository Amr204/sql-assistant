"""``/api/v1/status`` aggregates readiness for the web UI."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vai_agent.bootstrap import create_app


def test_api_v1_status_schema() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/api/v1/status")
    assert r.status_code == 200
    data = r.json()
    keys = {
        "status",
        "app",
        "version",
        "profile_id",
        "profile_ready",
        "agent_ready",
        "memory_ready",
        "tools_ready",
        "llm_ready",
        "errors",
    }
    assert set(data.keys()) == keys
    assert isinstance(data["errors"], list)
