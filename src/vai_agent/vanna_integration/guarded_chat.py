"""Vanna :class:`~vanna.servers.base.chat_handler.ChatHandler` with shared HTTP controls.

Overrides :meth:`handle_stream` so poll, SSE, and WebSocket routes all enforce the
same checks before :meth:`~vanna.core.agent.Agent.send_message` runs.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from vanna.core.agent import Agent
from vanna.servers.base import ChatHandler, ChatRequest, ChatStreamChunk

from vai_agent.api.rate_limit import get_rate_limiter
from vai_agent.config.settings import Settings
from vai_agent.security.audit_log import emit_audit_record
from vai_agent.security.prompt_injection import check_prompt_injection
from vai_agent.users import UserResolutionError


class GuardedChatHandler(ChatHandler):
    """``ChatHandler`` subclass: user resolution, limits, injection, audit, then agent."""

    def __init__(self, agent: Agent, settings: Settings) -> None:
        super().__init__(agent)
        self._settings = settings
        self._limiter = get_rate_limiter()

    def _request_id(self, request: ChatRequest) -> str:
        rid = request.request_id or str(uuid.uuid4())
        return str(rid)

    def _remote_ip(self, request: ChatRequest) -> str:
        rc = request.request_context
        if rc.remote_addr:
            return str(rc.remote_addr)
        meta = rc.metadata or {}
        return str(meta.get("remote_ip", "unknown"))

    async def handle_stream(  # type: ignore[override]
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        rc = request.request_context
        if rc is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing request_context.",
            )

        request_id = self._request_id(request)
        question = request.message or ""
        started = time.perf_counter()

        try:
            user = await self.agent.user_resolver.resolve_user(rc)
        except UserResolutionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

        user_id = str(user.id)
        groups = list(getattr(user, "group_memberships", []) or [])
        remote_ip = self._remote_ip(request)

        decision = self._limiter.allow_request(
            user_id=user_id,
            ip=remote_ip,
            groups=groups,
            settings=self._settings,
        )
        if not decision.allowed:
            emit_audit_record(
                {
                    "kind": "chat",
                    "request_id": request_id,
                    "user_id": user_id,
                    "access_groups": groups,
                    "decision": "rejected",
                    "reason": decision.reason,
                    "control": "rate_limit",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=decision.reason or "Rate limit exceeded.",
            )

        conc_key = f"user:{user_id}"
        conc = self._limiter.try_acquire_concurrency(
            conc_key,
            limit=self._settings.rate_limit_max_concurrent_per_user,
        )
        if not conc.allowed:
            emit_audit_record(
                {
                    "kind": "chat",
                    "request_id": request_id,
                    "user_id": user_id,
                    "access_groups": groups,
                    "decision": "rejected",
                    "reason": conc.reason,
                    "control": "concurrency_limit",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=conc.reason or "Concurrent request limit exceeded.",
            )

        stream_ok = False
        try:
            injection = check_prompt_injection(question)
            if not injection.allowed:
                emit_audit_record(
                    {
                        "kind": "chat",
                        "request_id": request_id,
                        "user_id": user_id,
                        "access_groups": groups,
                        "decision": "rejected",
                        "reason": injection.reason,
                        "control": "prompt_injection",
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Question rejected by safety policy.",
                )

            emit_audit_record(
                {
                    "kind": "chat",
                    "request_id": request_id,
                    "user_id": user_id,
                    "access_groups": groups,
                    "decision": "accepted",
                    "control": "guarded_chat_handler",
                },
            )

            conversation_id = request.conversation_id or self._generate_conversation_id()

            async for component in self.agent.send_message(
                request_context=rc,
                message=question,
                conversation_id=conversation_id,
            ):
                yield ChatStreamChunk.from_component(
                    component,
                    conversation_id,
                    request_id,
                )
            stream_ok = True

        except HTTPException:
            raise

        except Exception:
            emit_audit_record(
                {
                    "kind": "chat",
                    "request_id": request_id,
                    "user_id": user_id,
                    "access_groups": groups,
                    "decision": "error",
                    "error_type": "Exception",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise

        finally:
            self._limiter.release_concurrency(conc_key)

        if stream_ok:
            emit_audit_record(
                {
                    "kind": "chat",
                    "request_id": request_id,
                    "user_id": user_id,
                    "access_groups": groups,
                    "decision": "completed",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
