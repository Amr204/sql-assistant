"""Serving ``/`` redirect and ``/app`` SPA or build placeholder."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vai_agent.bootstrap import create_app


def test_root_redirects_to_app() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert (r.headers.get("location") or "").endswith("/app")


def test_app_returns_200() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/app")
    assert r.status_code == 200
    body = r.text.lower()
    assert "vanna-components" not in body
    assert "img.vanna.ai" not in body
