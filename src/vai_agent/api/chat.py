"""``POST /chat`` — :class:`~vai_agent.vanna_integration.guarded_chat.GuardedChatHandler` → Vanna agent."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from vanna.core.user.request_context import RequestContext
from vanna.servers.base import ChatRequest as VannaChatRequest

from vai_agent.config.settings import get_settings
from vai_agent.vanna_integration.guarded_chat import GuardedChatHandler
from vai_agent.vanna_integration.runtime import VaiVannaRuntime

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: str | None = None
    request_id: str
    result: dict[str, Any]


def _require_runtime(request: Request) -> VaiVannaRuntime:
    runtime = getattr(request.app.state, "agent", None)
    if runtime is None or not isinstance(runtime, VaiVannaRuntime):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not configured.",
        )
    return runtime


def _request_context(request: Request, metadata: dict[str, Any]) -> RequestContext:
    return RequestContext(
        cookies=dict(request.cookies),
        headers={k: v for k, v in request.headers.items()},
        remote_addr=request.client.host if request.client else None,
        query_params=dict(request.query_params),
        metadata=metadata,
    )


@router.post("/chat", response_model=ChatResponse, summary="Ask via Vanna Agent workflow")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    runtime = _require_runtime(request)
    settings = get_settings()
    request_id = uuid.uuid4().hex

    metadata = {
        **body.metadata,
        "request_id": request_id,
        "source": "custom_chat_endpoint",
        "remote_ip": request.client.host if request.client else "unknown",
    }
    rc = _request_context(request, metadata)

    vanna_request = VannaChatRequest(
        message=body.question,
        conversation_id=body.conversation_id,
        request_id=request_id,
        request_context=rc,
        metadata=metadata,
    )

    handler = GuardedChatHandler(runtime.vanna, settings)
    response = await handler.handle_poll(vanna_request)

    return ChatResponse(
        conversation_id=response.conversation_id,
        request_id=response.request_id or request_id,
        result=response.model_dump(mode="json"),
    )
