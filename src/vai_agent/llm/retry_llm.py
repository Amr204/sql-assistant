"""Retry + optional fallback model for Vanna :class:`~vanna.core.llm.LlmService`."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from vanna.core.llm import LlmRequest, LlmResponse, LlmService, LlmStreamChunk

logger = logging.getLogger(__name__)

_RETRYABLE = (
    httpx.HTTPStatusError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


class RetryLlmService(LlmService):
    """Delegates to an inner :class:`LlmService` with exponential-backoff retries."""

    def __init__(
        self,
        inner: LlmService,
        *,
        fallback: LlmService | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._inner = inner
        self._fallback = fallback
        self._max_attempts = max_attempts

    async def send_request(self, request: LlmRequest) -> LlmResponse:
        """Send request."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    return await self._inner.send_request(request)
        except _RETRYABLE:
            if self._fallback is None:
                raise
            logger.warning("primary LLM failed after retries; trying fallback model")
            return await self._fallback.send_request(request)
        raise RuntimeError("unreachable")  # pragma: no cover

    async def stream_request(self, request: LlmRequest) -> AsyncGenerator[LlmStreamChunk, None]:
        """Stream response with single-attempt fallback.

        Note: Unlike ``send_request``, streaming does NOT use exponential backoff
        because partially-yielded chunks cannot be rolled back. The consumer must
        handle potential duplicate content if the primary fails mid-stream and the
        fallback is invoked.
        """
        last_exc: BaseException | None = None
        try:
            async for chunk in self._inner.stream_request(request):
                yield chunk
            return
        except _RETRYABLE as exc:
            last_exc = exc
            logger.warning("Primary stream failed, trying fallback: %s", exc)

        if self._fallback is not None:
            try:
                async for chunk in self._fallback.stream_request(request):
                    yield chunk
                return
            except _RETRYABLE as exc:
                logger.error("Fallback stream also failed: %s", exc)
                raise

        if last_exc is not None:
            raise last_exc

    async def validate_tools(self, tools: list[Any]) -> list[str]:
        """Validate tools."""
        return await self._inner.validate_tools(tools)
