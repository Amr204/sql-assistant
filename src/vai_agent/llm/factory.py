"""Construct an LLM client from application settings."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vai_agent.llm.base import ChatCompletionClient
from vai_agent.llm.openrouter_service import OpenRouterChatService

if TYPE_CHECKING:
    from vai_agent.config.settings import Settings


def build_chat_completion_client(settings: Settings) -> ChatCompletionClient | None:
    """Return a configured client, or ``None`` when LLM usage is disabled.

    When ``llm_provider`` is ``openrouter`` but credentials are absent, the
    app still boots; callers see ``None`` and a warning is logged once.
    """

    from vai_agent.config.settings import LlmProvider

    logger = logging.getLogger(__name__)

    if settings.llm_provider is LlmProvider.none:
        return None

    if settings.llm_provider is not LlmProvider.openrouter:
        logger.warning(
            "Unknown llm_provider %r; no LLM client will be constructed.",
            settings.llm_provider,
        )
        return None

    key_secret = settings.openrouter_api_key
    if key_secret is None or not key_secret.get_secret_value().strip():
        logger.warning(
            "LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is unset; skipping LLM client.",
        )
        return None

    model_id = settings.openrouter_model.strip()
    if not model_id:
        logger.warning("OPENROUTER_MODEL is empty; skipping LLM client.")
        return None

    base_stripped = settings.openrouter_base_url.strip()
    return OpenRouterChatService(
        api_key=key_secret.get_secret_value(),
        model=model_id,
        base_url=base_stripped or None,
        timeout_seconds=float(settings.llm_http_timeout_seconds),
        referer_header=(settings.openrouter_http_referer or "").strip() or None,
    )
