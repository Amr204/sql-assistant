"""Pytest fixtures shared across the suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from vai_agent.bootstrap import create_app
from vai_agent.config.settings import Settings, get_settings


@pytest.fixture()
def settings() -> Iterator[Settings]:
    """Yield a fresh ``Settings`` instance and reset the cache afterwards."""

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Yield a FastAPI ``TestClient`` bound to a freshly built app."""

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
