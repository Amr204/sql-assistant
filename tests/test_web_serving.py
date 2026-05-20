"""SPA static file routing under ``/app``."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vai_agent.web.serving import register_web_routes


@pytest.fixture()
def spa_client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>app</body></html>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('ok');", encoding="utf-8")

    app = FastAPI()
    register_web_routes(app, web_dist_dir=str(dist))
    return TestClient(app)


def test_spa_index_served(spa_client: TestClient) -> None:
    r = spa_client.get("/app")
    assert r.status_code == 200
    assert "app" in r.text


def test_existing_static_asset_served(spa_client: TestClient) -> None:
    r = spa_client.get("/app/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_missing_js_returns_404_not_spa_shell(spa_client: TestClient) -> None:
    r = spa_client.get("/app/assets/missing.js")
    assert r.status_code == 404
    assert r.json()["detail"] == "Static asset not found"


def test_unknown_client_route_falls_back_to_index(spa_client: TestClient) -> None:
    r = spa_client.get("/app/settings/profile")
    assert r.status_code == 200
    assert "app" in r.text
