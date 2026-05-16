"""FastAPI routes for the agent.

* ``GET  /agent/tools``                    — list of tools visible to the caller
* ``POST /agent/tools/{tool_name}/invoke`` — invoke a tool

The router reads the agent from ``request.app.state.agent``. If no
agent is attached (e.g. the app was started without a profile or DB
configuration) every route returns ``503 Service Unavailable``. Tests
inject a stub agent into ``app.state.agent`` to exercise the endpoints
without a real database.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from vai_agent.tools.base import ToolResult
from vai_agent.users import UserResolutionError
from vai_agent.vai_app.agent_factory import Agent

router = APIRouter(prefix="/agent", tags=["agent"])


def _require_agent(request: Request) -> Agent:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not configured for this deployment.",
        )
    return agent


def _resolve_user(agent: Agent, request: Request):
    try:
        return agent.user_resolver.resolve(dict(request.headers))
    except UserResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class ToolDescriptor(BaseModel):
    """One entry of the ``GET /agent/tools`` response."""

    name: str
    description: str
    access_groups: list[str]
    args_schema: dict[str, Any]


class ToolListResponse(BaseModel):
    tools: list[ToolDescriptor]


class InvokeRequest(BaseModel):
    """Request body for ``POST /agent/tools/{name}/invoke``."""

    args: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/tools", response_model=ToolListResponse, summary="List available tools")
def list_tools(request: Request) -> ToolListResponse:
    agent = _require_agent(request)
    user = _resolve_user(agent, request)
    tools = [
        ToolDescriptor(
            name=t.name,
            description=t.description,
            access_groups=list(t.access_groups),
            args_schema=t.args_model.model_json_schema(),
        )
        for t in agent.registry.list_for_user(user)
    ]
    return ToolListResponse(tools=tools)


@router.post(
    "/tools/{tool_name}/invoke",
    response_model=ToolResult,
    summary="Invoke a tool",
)
def invoke_tool(
    tool_name: str,
    body: InvokeRequest,
    request: Request,
) -> ToolResult:
    agent = _require_agent(request)
    user = _resolve_user(agent, request)
    return agent.invoke(tool_name, body.args, user)
