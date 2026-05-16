"""Tests for the ``GET /health`` endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


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
