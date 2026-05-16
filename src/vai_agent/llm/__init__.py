"""OpenAI-compatible LLM clients."""

from vai_agent.llm.base import ChatCompletionClient, ChatCompletionResult, ChatMessage
from vai_agent.llm.errors import LlmError, LlmUpstreamError
from vai_agent.llm.factory import build_chat_completion_client
from vai_agent.llm.openrouter_service import OpenRouterChatService

__all__ = [
    "ChatCompletionClient",
    "ChatCompletionResult",
    "ChatMessage",
    "LlmError",
    "LlmUpstreamError",
    "OpenRouterChatService",
    "build_chat_completion_client",
]
