"""Inject :class:`~vai_agent.vai_app.context_enhancer.ContextEnhancer` output into Vanna LLM prompts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from vanna.core.enhancer import LlmContextEnhancer
from vanna.core.llm.models import LlmMessage
from vanna.core.user.models import User as VannaUser

from vai_agent.users import User as VaiUser
from vai_agent.vai_app.context_enhancer import ContextEnhancer

if TYPE_CHECKING:
    pass


class ProfileLlmContextEnhancer(LlmContextEnhancer):
    """Adds profile-derived context (schema, glossary, security) to the system prompt."""

    def __init__(self, enhancer: ContextEnhancer) -> None:
        self._enhancer = enhancer

    async def enhance_system_prompt(
        self, system_prompt: str, user_message: str, user: VannaUser
    ) -> str:
        vai_user = VaiUser(
            id=user.id,
            email=user.email,
            groups=tuple(user.group_memberships),
        )

        def _build() -> object:
            return self._enhancer.enhance(user_message, vai_user)

        result = await asyncio.to_thread(_build)
        block = result.context_text.strip()
        if not block:
            return system_prompt
        return f"{system_prompt}\n\n## Retrieved profile context\n{block}"

    async def enhance_user_messages(
        self, messages: list[LlmMessage], user: VannaUser
    ) -> list[LlmMessage]:
        return messages
