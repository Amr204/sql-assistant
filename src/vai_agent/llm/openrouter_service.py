"""OpenRouter client using the OpenAI-compatible HTTP API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from vai_agent.llm.base import ChatCompletionResult, ChatMessage
from vai_agent.llm.errors import LlmUpstreamError

logger = logging.getLogger(__name__)

_DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterChatService:
    """POST ``/chat/completions`` against OpenRouter (or compatible base URL)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 120.0,
        referer_header: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            msg = "OpenRouter api_key is empty."
            raise ValueError(msg)
        self._model = model
        self._base = (base_url or _DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self._timeout = timeout_seconds
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }
        if referer_header:
            self._headers["HTTP-Referer"] = referer_header

        self._client = http_client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenRouterChatService:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def chat_completion(self, messages: tuple[ChatMessage, ...]) -> ChatCompletionResult:
        if not messages:
            msg = "messages must not be empty"
            raise ValueError(msg)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump() for m in messages],
        }
        url = f"{self._base}/chat/completions"

        try:
            response = self._client.post(url, json=payload, headers=self._headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "OpenRouter HTTP error",
                extra={"status": exc.response.status_code},
            )
            raise LlmUpstreamError("OpenRouter returned an HTTP error.") from exc
        except Exception as exc:  # pragma: no cover — network variance
            logger.warning("OpenRouter request failed", extra={"exc_type": type(exc).__name__})
            raise LlmUpstreamError("Unable to reach the LLM endpoint.") from exc

        choice0 = ((data.get("choices") or [])[:1] or [{}])[0]
        message = choice0.get("message") if isinstance(choice0, dict) else None
        content = message.get("content") if isinstance(message, dict) else None

        model_used = str(data.get("model") or self._model)
        finish_reason = (
            choice0.get("finish_reason") if isinstance(choice0, dict) else None
        )

        if not isinstance(content, str) or not content.strip():
            raise LlmUpstreamError("Malformed chat completion payload from provider.")

        return ChatCompletionResult(
            content=content.strip(),
            model_used=model_used,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )
