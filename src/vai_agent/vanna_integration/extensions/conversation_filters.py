"""Conversation ingress filters for SQL Assistant.

These filters run before requests reach the Vanna agent, SQL-fast path, or LLM.
They are defense-in-depth checks only. SQL policy and PII policy remain the
final enforcement layer before database execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vai_agent.security.prompt_injection import check_prompt_injection


@dataclass(frozen=True)
class ConversationFilterResult:
    """Result of validating a user conversation request."""

    allowed: bool
    reason: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class ConversationIngressLimits:
    """Limits for incoming chat requests before agent execution."""

    max_message_chars: int = 20_000
    max_metadata_keys: int = 50
    max_metadata_depth: int = 3
    max_metadata_string_chars: int = 2_000


class ConversationIngressFilter:
    """Validate user input before it reaches Vanna or SQL-fast execution."""

    def __init__(self, limits: ConversationIngressLimits | None = None) -> None:
        self._limits = limits or ConversationIngressLimits()

    def check_message(
        self,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> ConversationFilterResult:
        text = message.strip()

        if not text:
            return ConversationFilterResult(
                allowed=False,
                code="EMPTY_MESSAGE",
                reason="Question is empty.",
            )

        if len(text) > self._limits.max_message_chars:
            return ConversationFilterResult(
                allowed=False,
                code="MESSAGE_TOO_LARGE",
                reason="Question is too large.",
            )

        injection = check_prompt_injection(text)
        if not injection.allowed:
            return ConversationFilterResult(
                allowed=False,
                code="PROMPT_INJECTION",
                reason="Question contains unsafe prompt-injection patterns.",
            )

        metadata_result = self._check_metadata(metadata or {})
        if not metadata_result.allowed:
            return metadata_result

        return ConversationFilterResult(allowed=True)

    def _check_metadata(self, metadata: Mapping[str, Any]) -> ConversationFilterResult:
        if len(metadata) > self._limits.max_metadata_keys:
            return ConversationFilterResult(
                allowed=False,
                code="METADATA_TOO_MANY_KEYS",
                reason="Request metadata has too many keys.",
            )

        if not self._is_safe_metadata(metadata, depth=0):
            return ConversationFilterResult(
                allowed=False,
                code="METADATA_TOO_LARGE_OR_DEEP",
                reason="Request metadata is too large or too deeply nested.",
            )

        return ConversationFilterResult(allowed=True)

    def _is_safe_metadata(self, value: Any, *, depth: int) -> bool:
        if depth > self._limits.max_metadata_depth:
            return False

        if isinstance(value, str):
            return len(value) <= self._limits.max_metadata_string_chars

        if isinstance(value, (int, float, bool)) or value is None:
            return True

        if isinstance(value, Mapping):
            if len(value) > self._limits.max_metadata_keys:
                return False
            return all(
                isinstance(k, str)
                and len(k) <= 100
                and self._is_safe_metadata(v, depth=depth + 1)
                for k, v in value.items()
            )

        if isinstance(value, list):
            if len(value) > self._limits.max_metadata_keys:
                return False
            return all(self._is_safe_metadata(v, depth=depth + 1) for v in value)

        return False
