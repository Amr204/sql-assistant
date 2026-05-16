"""LLM abstraction — OpenAI-compatible chat completions."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """Single message in OpenAI-compatible chat format."""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionResult(BaseModel):
    """Normalised assistant reply from any OpenAI-compatible provider."""

    model_config = ConfigDict(frozen=True)

    content: str
    model_used: str
    finish_reason: str | None = None


@runtime_checkable
class ChatCompletionClient(Protocol):
    """Thin protocol for callers that only need synchronous chat completions."""

    def chat_completion(self, messages: tuple[ChatMessage, ...]) -> ChatCompletionResult:
        """Blocking request; raises :class:`~vai_agent.llm.errors.LlmError` on failure."""
