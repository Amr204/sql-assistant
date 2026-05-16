"""Lightweight prompt-injection / instruction-override heuristics.

This is not a substitute for model-level safety; it blocks obvious
attempts to override system behaviour before they reach the LLM or tools.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BLOCKED = re.compile(
    r"(?is)\b("
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions?"
    r"|system\s*:\s*"
    r"you\s+are\s+now"
    r"|forget\s+(everything|all)"
    r"|<\s*script"
    r"|javascript\s*:"
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
