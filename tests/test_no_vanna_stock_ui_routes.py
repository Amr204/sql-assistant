"""Vanna stock UI routes must not be registered."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vai_agent.bootstrap import create_app


def test_vanna_chat_poll_returns_404() -> None:
    with TestClient(create_app()) as client:
        r = client.post("/api/vanna/v2/chat_poll", json={"message": "x"})
    assert r.status_code == 404


def test_vanna_chat_sse_returns_404() -> None:
    with TestClient(create_app()) as client:
        r = client.post("/api/vanna/v2/chat_sse", json={"message": "x"})
    assert r.status_code == 404


def test_vanna_chat_websocket_not_registered() -> None:
    app = create_app()
    ws_paths: list[str] = []
    for route in app.routes:
        cls = type(route).__name__
        if "WebSocket" in cls:
            path = getattr(route, "path", "") or ""
            ws_paths.append(path)
    assert "/api/vanna/v2/chat_websocket" not in ws_paths


def test_root_redirect_does_not_serve_vanna_stock_html() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    loc = r.headers.get("location") or ""
    assert loc.endswith("/app")
    text = (r.text or "").lower()
    assert "vanna-components" not in text


def test_app_placeholder_has_no_vanna_cdn() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/app", follow_redirects=False)
    assert r.status_code == 200
    body = r.text.lower()
    assert "vanna-components.js" not in body
    assert "img.vanna.ai" not in body
