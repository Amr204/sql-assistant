"""Health-check endpoint.

Phase 1 deliberately exposes a *liveness* probe only. A separate
``/ready`` (readiness) probe will be added in a later phase once the
agent has external dependencies (DB, memory store, LLM) whose state is
meaningful to surface.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from vai_agent.config.settings import AppEnv, Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model for ``GET /health``."""

    status: str = Field(description="Always 'ok' when the process is serving requests.")
    app: str = Field(description="Service name.")
    version: str = Field(description="Service version.")
    env: AppEnv = Field(description="Deployment environment.")


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    """Return basic liveness information.

    This endpoint must remain dependency-free so that orchestrators can
    use it as a true liveness signal — it should answer ``ok`` whenever
    the Python process is up, regardless of downstream availability.
    """

    settings: Settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
    )
