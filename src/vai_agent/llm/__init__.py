"""LLM-related types and deprecated factory hooks."""

from vai_agent.llm.base import ChatCompletionClient, ChatCompletionResult, ChatMessage
from vai_agent.llm.errors import LlmError, LlmUpstreamError
from vai_agent.llm.factory import build_chat_completion_client

__all__ = [
    "ChatCompletionClient",
    "ChatCompletionResult",
    "ChatMessage",
    "LlmError",
    "LlmUpstreamError",
    "build_chat_completion_client",
]
