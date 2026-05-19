from __future__ import annotations

from fastapi import APIRouter, Request

from vai_agent.api.v1.schemas import StatusResponse
from vai_agent.config.settings import get_settings

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=StatusResponse)
def get_status(request: Request) -> StatusResponse:
    settings = get_settings()
    readiness = getattr(request.app.state, "readiness", None) or {}
    profile_ready = bool(readiness.get("profile_ready"))
    agent_ready = bool(readiness.get("agent_ready"))
    memory_ready = bool(readiness.get("memory_ready"))
    tools_ready = bool(readiness.get("tools_ready"))
    llm_ready = bool(readiness.get("llm_ready"))
    fully_ready = bool(readiness.get("ready"))
    errors = [str(e) for e in readiness.get("errors", [])]

    return StatusResponse(
        status="ok" if fully_ready else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        profile_id=settings.db_profile_id,
        profile_ready=profile_ready,
        agent_ready=agent_ready,
        memory_ready=memory_ready,
        tools_ready=tools_ready,
        llm_ready=llm_ready,
        errors=errors,
    )
