"""``/api/v1/profile`` returns only safe profile metadata."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from vai_agent.bootstrap import create_app


def test_api_v1_profile_no_secrets() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/api/v1/profile")
    if r.status_code == 503:
        return
    assert r.status_code == 200
    raw = json.dumps(r.json()).lower()
    forbidden = (
        "password",
        "connection_string",
        "connection string",
        "db_username",
        "db_password",
        "jdbc",
        "mongodb",
    )
    for token in forbidden:
        assert token not in raw
    body = r.json()
    assert "profile_id" in body
    assert "display_name" in body
    assert "dialect" in body
    assert "table_count" in body
    assert "allowed_groups" in body
