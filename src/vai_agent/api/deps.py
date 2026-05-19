"""Shared FastAPI dependencies for API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from vanna.core.user.request_context import RequestContext

from vai_agent.vanna_integration.runtime import VaiVannaRuntime


def require_runtime(request: Request) -> VaiVannaRuntime:
    """Return the initialised Vanna runtime or raise 503."""
    runtime = getattr(request.app.state, "agent", None)
    if not isinstance(runtime, VaiVannaRuntime):
        readiness = getattr(request.app.state, "readiness", {}) or {}
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AGENT_NOT_READY",
                "message": "Agent is not ready.",
                "readiness": readiness,
            },
        )
    return runtime


def build_request_context(request: Request, metadata: dict[str, Any]) -> RequestContext:
    """Build Vanna :class:`RequestContext` from the incoming HTTP request."""
    return RequestContext(
        cookies=dict(request.cookies),
        headers={k: v for k, v in request.headers.items()},
        remote_addr=request.client.host if request.client else None,
        query_params=dict(request.query_params),
        metadata=metadata,
    )
