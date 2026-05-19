"""Token counting for context budget (tiktoken with fallback)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ENCODING = None


def _encoding():
    global _ENCODING
    if _ENCODING is None:
        import tiktoken

        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def count_tokens(text: str) -> int:
    """Accurate token count using tiktoken (cl100k_base), with mixed-text fallback."""
    if not text:
        return 0
    try:
        return len(_encoding().encode(text))
    except Exception:
        logger.debug("tiktoken encode failed; using char fallback", exc_info=True)
        return max(1, int(len(text) * 0.5))
