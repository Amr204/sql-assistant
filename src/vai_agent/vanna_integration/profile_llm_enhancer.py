"""Inject profile RAG context from :class:`~vai_agent.vai_app.context_enhancer.ContextEnhancer`."""

from __future__ import annotations

import asyncio

from vanna.core.enhancer import LlmContextEnhancer
from vanna.core.llm.models import LlmMessage
from vanna.core.user.models import User as VannaUser

from vai_agent.users import User as VaiUser
from vai_agent.vai_app.context_enhancer import ContextEnhancer
from vai_agent.vanna_integration.extensions.system_prompt import (
    sql_server_generation_rules,
    task_prefix_for_question,
)


class ProfileLlmContextEnhancer(LlmContextEnhancer):
    """Appends retrieved profile context (schema, glossary, examples) to the system prompt."""

    def __init__(self, enhancer: ContextEnhancer) -> None:
        self._enhancer = enhancer

    async def enhance_system_prompt(
        self, system_prompt: str, user_message: str, user: VannaUser
    ) -> str:
        """Enhance system prompt with RAG blocks; stable rules come from system_prompt."""
        vai_user = VaiUser(
            id=user.id,
            email=user.email,
            groups=tuple(user.group_memberships),
        )

        def _build() -> object:
            return self._enhancer.enhance(user_message, vai_user)

        result = await asyncio.to_thread(_build)
        rules = sql_server_generation_rules()
        block = result.context_text.strip()
        if not block:
            return f"{system_prompt}\n\n{rules}"

        prefix = task_prefix_for_question(user_message)
        return (
            f"{system_prompt}\n\n"
            f"{prefix}## Retrieved profile context\n{block}\n\n{rules}"
        )

    async def enhance_user_messages(
        self, messages: list[LlmMessage], user: VannaUser
    ) -> list[LlmMessage]:
        """Enhance user messages."""
        return messages
