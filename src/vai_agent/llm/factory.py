"""Construct an LLM client from application settings (deprecated stub)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vai_agent.llm.base import ChatCompletionClient

if TYPE_CHECKING:
    from vai_agent.config.settings import Settings


def build_chat_completion_client(settings: Settings) -> ChatCompletionClient | None:
    """Return ``None``.

    The legacy httpx OpenAI-compatible client was removed; production chat
    uses Vanna's ``LlmService`` (:mod:`vai_agent.vanna_integration.model_llm`).
    This entry point remains so imports and older tests keep working.
    """

    _ = settings
    logging.getLogger(__name__).warning(
        "build_chat_completion_client is deprecated and always returns None; "
        "use the Vanna LLM stack instead.",
    )
    return None
