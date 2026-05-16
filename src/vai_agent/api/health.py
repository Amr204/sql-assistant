"""Health-check endpoint.

Phase 1 deliberately exposes a *liveness* probe only. A separate
``/ready`` (readiness) probe will be added in a later phase once the
agent has external dependencies (DB, memory store, LLM) whose state is
meaningful to surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vai_agent.config.settings import AppEnv, Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model for ``GET /health``."""

    status: str = Field(description="Always 'ok' when the process is serving requests.")
    app: str = Field(description="Service name.")
    version: str = Field(description="Service version.")
    env: AppEnv = Field(description="Deployment environment.")


class ReadyResponse(BaseModel):
    """Response model for ``GET /ready``."""

    status: str = Field(description="'ok' when fully ready, otherwise 'degraded'.")
    profile_ready: bool
    agent_ready: bool
    memory_ready: bool
    tools_ready: bool = False
    llm_ready: bool = False
    errors: list[str] = Field(default_factory=list)


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


@router.get("/ready", response_model=ReadyResponse, summary="Readiness probe")
def ready(request: Request) -> ReadyResponse | JSONResponse:
    readiness = getattr(request.app.state, "readiness", None) or {}
    response = ReadyResponse(
        status="ok" if readiness.get("ready") else "degraded",
        profile_ready=bool(readiness.get("profile_ready")),
        agent_ready=bool(readiness.get("agent_ready")),
        memory_ready=bool(readiness.get("memory_ready")),
        tools_ready=bool(readiness.get("tools_ready")),
        llm_ready=bool(readiness.get("llm_ready")),
        errors=[str(e) for e in readiness.get("errors", [])],
    )
    if response.status == "ok":
        return response
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )
