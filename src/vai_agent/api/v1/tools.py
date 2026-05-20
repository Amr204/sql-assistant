from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from vai_agent.api.deps import build_request_context, require_runtime
from vai_agent.api.v1.schemas import ToolDescriptorResponse, ToolsListResponse
from vai_agent.users import UserResolutionError

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=ToolsListResponse)
async def list_tools(request: Request) -> ToolsListResponse:
    """List tools."""
    runtime = require_runtime(request)
    rc = build_request_context(request, {})
    try:
        v_user = await runtime.vanna.user_resolver.resolve_user(rc)
    except UserResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    schemas = await runtime.vanna.tool_registry.get_schemas(v_user)
    tools = [
        ToolDescriptorResponse(
            name=s.name,
            description=s.description,
            access_groups=list(s.access_groups),
            args_schema=s.parameters,
        )
        for s in schemas
    ]
    return ToolsListResponse(tools=tools)
