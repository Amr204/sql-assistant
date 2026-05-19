"""Build Vanna :class:`~vanna.core.llm.LlmService` with retries and optional fallback."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vanna.integrations.mock import MockLlmService
from vanna.integrations.openai import OpenAILlmService

from vai_agent.llm.retry_llm import RetryLlmService

if TYPE_CHECKING:
    from vai_agent.config.settings import Settings

logger = logging.getLogger(__name__)


def build_vanna_llm_service(settings: Settings) -> object:
    """Return a Vanna :class:`~vanna.core.llm.base.LlmService` implementation."""

    from vai_agent.config.settings import LlmProvider

    if settings.model_provider is not LlmProvider.openai_compatible:
        return MockLlmService(
            response_content="LLM is disabled (MODEL_PROVIDER!=openai_compatible).",
        )

    key = settings.effective_model_api_key
    if key is None or not key.get_secret_value().strip():
        logger.warning(
            "openai_compatible selected but MODEL_API_KEY is unset; using mock LLM.",
        )
        return MockLlmService(response_content="MODEL_API_KEY is not configured.")

    model = settings.effective_model_name
    if not model:
        logger.warning("MODEL_NAME is empty; using mock LLM.")
        return MockLlmService(response_content="MODEL_NAME is not configured.")

    primary = OpenAILlmService(
        model=model,
        api_key=key.get_secret_value(),
        base_url=settings.effective_model_base_url,
    )

    fallback_name = settings.model_fallback_name.strip()
    fallback_svc = None
    if fallback_name:
        fallback_svc = OpenAILlmService(
            model=fallback_name,
            api_key=key.get_secret_value(),
            base_url=settings.effective_model_base_url,
        )

    return RetryLlmService(primary, fallback=fallback_svc)
