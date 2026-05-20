"""Lightweight prompt-injection / instruction-override heuristics.

This is not a substitute for model-level safety or :class:`~vai_agent.security.sql_policy.SqlPolicyEngine`;
it blocks obvious attempts to override system behaviour before they reach the LLM or tools.
SQL execution remains gated by policy regardless of this check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BLOCKED = re.compile(
    r"(?is)\b("
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions?"
    r"|disregard\s+(all\s+)?(previous|prior)\s+instructions?"
    r"|system\s*:\s*"
    r"|assistant\s*:\s*"
    r"|you\s+are\s+now"
    r"|forget\s+(everything|all|your)"
    r"|new\s+instructions?\s*:"
    r"|override\s+(the\s+)?(system|safety)"
    r"|jailbreak"
    r"|do\s+anything\s+now"
    r"|<\s*script"
    r"|javascript\s*:"
    r"|data\s*:\s*text/html"
    r")\b"
)


@dataclass(frozen=True)
class PromptInjectionResult:
    """Outcome of :func:`check_prompt_injection`."""

    allowed: bool
    reason: str | None = None


def check_prompt_injection(text: str) -> PromptInjectionResult:
    """Return ``allowed=False`` when *text* matches blocked patterns."""

    if not text or not text.strip():
        return PromptInjectionResult(False, "empty_question")
    if _BLOCKED.search(text):
        return PromptInjectionResult(False, "suspected_prompt_injection")
    return PromptInjectionResult(True, None)
