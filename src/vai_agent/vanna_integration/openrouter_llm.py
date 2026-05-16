"""Build ``vanna.integrations.openai.llm.OpenAILlmService`` pointed at OpenRouter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vanna.integrations.mock import MockLlmService
from vanna.integrations.openai import OpenAILlmService

if TYPE_CHECKING:
    from vai_agent.config.settings import Settings

logger = logging.getLogger(__name__)


def build_vanna_llm_service(settings: Settings) -> object:
    """Return a Vanna :class:`~vanna.core.llm.base.LlmService` implementation.

    Uses :class:`~vanna.integrations.openai.llm.OpenAILlmService` with
    ``base_url`` + key from settings when ``LLM_PROVIDER=openrouter`` and
    credentials are present.  Otherwise returns :class:`MockLlmService`
    so the process can boot without remote keys (tests / local).
    """

    from vai_agent.config.settings import LlmProvider

    if settings.llm_provider is not LlmProvider.openrouter:
        return MockLlmService(
            response_content="LLM is disabled (LLM_PROVIDER!=openrouter).",
        )

    key = settings.openrouter_api_key
    if key is None or not key.get_secret_value().strip():
        logger.warning("openrouter selected but OPENROUTER_API_KEY is unset; using mock LLM.")
        return MockLlmService(response_content="OPENROUTER_API_KEY is not configured.")

    model = settings.openrouter_model.strip()
    if not model:
        logger.warning("OPENROUTER_MODEL is empty; using mock LLM.")
        return MockLlmService(response_content="OPENROUTER_MODEL is not configured.")

    return OpenAILlmService(
        model=model,
        api_key=key.get_secret_value(),
        base_url=settings.openrouter_base_url.strip() or None,
    )
