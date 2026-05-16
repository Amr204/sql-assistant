"""Register Vanna stock chat routes with HTTP status preservation.

Forked from ``vanna.servers.fastapi.routes`` (vanna 2.0.2) so
:class:`fastapi.HTTPException` raised by :class:`~vai_agent.vanna_integration.guarded_chat.GuardedChatHandler`
(401 / 400 / 429) is re-raised instead of being turned into a 500 response.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from vanna.core.user.request_context import RequestContext
from vanna.servers.base import ChatHandler, ChatRequest, ChatResponse
from vanna.servers.base.templates import get_index_html


def register_chat_routes(
    app: FastAPI,
    chat_handler: ChatHandler,
    config: dict[str, Any] | None = None,
) -> None:
    """Same paths as Vanna stock; ``HTTPException`` from handlers is not swallowed."""

    config = config or {}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        dev_mode = config.get("dev_mode", False)
        cdn_url = config.get("cdn_url", "https://img.vanna.ai/vanna-components.js")
        api_base_url = config.get("api_base_url", "")

        return get_index_html(
            dev_mode=dev_mode, cdn_url=cdn_url, api_base_url=api_base_url,
        )

    @app.post("/api/vanna/v2/chat_sse")
    async def chat_sse(
        chat_request: ChatRequest, http_request: Request,
    ) -> StreamingResponse:
        chat_request.request_context = RequestContext(
            cookies=dict(http_request.cookies),
            headers=dict(http_request.headers),
            remote_addr=http_request.client.host if http_request.client else None,
            query_params=dict(http_request.query_params),
            metadata=chat_request.metadata,
        )

        async def generate() -> AsyncGenerator[str, None]:
            try:
                async for chunk in chat_handler.handle_stream(chat_request):
                    chunk_json = chunk.model_dump_json()
                    yield f"data: {chunk_json}\n\n"
                yield "data: [DONE]\n\n"
            except HTTPException:
                raise
            except Exception as e:
                traceback.print_stack()
                traceback.print_exc()
                error_data = {
                    "type": "error",
                    "data": {"message": str(e)},
                    "conversation_id": chat_request.conversation_id or "",
                    "request_id": chat_request.request_id or "",
                }
                yield f"data: {json.dumps(error_data)}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.websocket("/api/vanna/v2/chat_websocket")
    async def chat_websocket(websocket: WebSocket) -> None:
        await websocket.accept()

        try:
            while True:
                try:
                    data = await websocket.receive_json()

                    metadata = data.get("metadata", {})
                    data["request_context"] = RequestContext(
                        cookies=dict(websocket.cookies),
                        headers=dict(websocket.headers),
                        remote_addr=websocket.client.host if websocket.client else None,
                        query_params=dict(websocket.query_params),
                        metadata=metadata,
                    )

                    chat_request = ChatRequest(**data)
                except Exception as e:
                    traceback.print_stack()
                    traceback.print_exc()
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": f"Invalid request: {e!s}"},
                        },
                    )
                    continue

                try:
                    async for chunk in chat_handler.handle_stream(chat_request):
                        await websocket.send_json(chunk.model_dump())

                    await websocket.send_json(
                        {
                            "type": "completion",
                            "data": {"status": "done"},
                            "conversation_id": chunk.conversation_id
                            if "chunk" in locals()
                            else "",
                            "request_id": chunk.request_id
                            if "chunk" in locals()
                            else "",
                        },
                    )

                except HTTPException as e:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": e.detail, "status_code": e.status_code},
                            "conversation_id": chat_request.conversation_id or "",
                            "request_id": chat_request.request_id or "",
                        },
                    )
                except Exception as e:
                    traceback.print_stack()
                    traceback.print_exc()
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": str(e)},
                            "conversation_id": chat_request.conversation_id or "",
                            "request_id": chat_request.request_id or "",
                        },
                    )

        except WebSocketDisconnect:
            pass
        except Exception as e:
            traceback.print_stack()
            traceback.print_exc()
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {"message": f"WebSocket error: {e!s}"},
                    },
                )
            except Exception:
                pass
            finally:
                await websocket.close()

    @app.post("/api/vanna/v2/chat_poll")
    async def chat_poll(
        chat_request: ChatRequest, http_request: Request,
    ) -> ChatResponse:
        chat_request.request_context = RequestContext(
            cookies=dict(http_request.cookies),
            headers=dict(http_request.headers),
            remote_addr=http_request.client.host if http_request.client else None,
            query_params=dict(http_request.query_params),
            metadata=chat_request.metadata,
        )

        try:
            result = await chat_handler.handle_poll(chat_request)
            return result
        except HTTPException:
            raise
        except Exception as e:
            traceback.print_stack()
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Chat failed: {e!s}") from e
