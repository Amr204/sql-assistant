"""FastAPI routes for the agent.

* ``GET  /agent/tools``                    — list of tools visible to the caller
* ``POST /agent/tools/{tool_name}/invoke`` — invoke a tool (via Vanna ``ToolRegistry``)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from vanna.core.tool import ToolCall, ToolContext

from vai_agent.api.deps import build_request_context, require_runtime
from vai_agent.config.settings import get_settings
from vai_agent.tools.base import ToolResult

from .rate_limit import get_rate_limiter

router = APIRouter(prefix="/agent", tags=["agent"])


async def _resolve_v_user(runtime: object, request: Request) -> object:
    from vai_agent.users import UserResolutionError

    rc = build_request_context(request, {})
    try:
        return await runtime.vanna.user_resolver.resolve_user(rc)
    except UserResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _vanna_tool_to_api(
    tool_name: str,
    *,
    success: bool,
    result_for_llm: str,
    error: str | None,
    metadata: dict[str, Any],
    request_id: str,
) -> ToolResult:
    data: dict[str, Any] = {}
    if success:
        try:
            data = json.loads(result_for_llm) if result_for_llm else {}
        except json.JSONDecodeError:
            data = {"text": result_for_llm}
    merged = {**metadata, "request_id": request_id}
    return ToolResult(
        success=success,
        tool=tool_name,
        data=data,
        error=error,
        metadata=merged,
    )


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
async def list_tools(request: Request) -> ToolListResponse:
    runtime = require_runtime(request)
    v_user = await _resolve_v_user(runtime, request)
    schemas = await runtime.vanna.tool_registry.get_schemas(v_user)
    tools = [
        ToolDescriptor(
            name=s.name,
            description=s.description,
            access_groups=list(s.access_groups),
            args_schema=s.parameters,
        )
        for s in schemas
    ]
    return ToolListResponse(tools=tools)


@router.post(
    "/tools/{tool_name}/invoke",
    response_model=ToolResult,
    summary="Invoke a tool",
)
async def invoke_tool(
    tool_name: str,
    body: InvokeRequest,
    request: Request,
) -> ToolResult:
    runtime = require_runtime(request)
    v_user = await _resolve_v_user(runtime, request)
    settings = get_settings()
    limiter = get_rate_limiter()
    remote_ip = request.client.host if request.client else "unknown"

    decision = limiter.allow_request(
        user_id=v_user.id,
        ip=remote_ip,
        groups=list(v_user.group_memberships),
        settings=settings,
    )
    if not decision.allowed:
        raise HTTPException(status_code=429, detail=decision.reason)

    conc_key = f"user:{v_user.id}"
    conc = limiter.try_acquire_concurrency(
        conc_key,
        limit=settings.rate_limit_max_concurrent_per_user,
    )
    if not conc.allowed:
        raise HTTPException(status_code=429, detail=conc.reason)

    request_id = uuid.uuid4().hex
    mem = runtime.vanna.agent_memory
    ctx = ToolContext(
        user=v_user,
        conversation_id="http-invoke",
        request_id=request_id,
        agent_memory=mem,
        metadata={
            "http": {
                "cookies": dict(request.cookies),
                "headers": {k: v for k, v in request.headers.items()},
                "remote_addr": request.client.host if request.client else None,
                "query_params": dict(request.query_params),
            },
        },
    )
    call = ToolCall(id=request_id, name=tool_name, arguments=body.args)
    try:
        res = await runtime.vanna.tool_registry.execute(call, ctx)
    finally:
        limiter.release_concurrency(conc_key)
    return _vanna_tool_to_api(
        tool_name,
        success=res.success,
        result_for_llm=res.result_for_llm,
        error=res.error,
        metadata=dict(res.metadata),
        request_id=request_id,
    )
