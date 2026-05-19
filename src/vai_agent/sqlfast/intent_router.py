"""Route clear data questions to the SQL fast path vs the full Vanna agent."""

from __future__ import annotations

import re
from enum import StrEnum

_AR_DATA_TOKENS: tuple[str, ...] = (
    "كم",
    "عدد",
    "اعرض",
    "أعرض",
    "عرض",
    "جيب",
    "أفضل",
    "افضل",
    "أضعف",
    "اضعف",
    "مبيعات",
    "عملاء",
    "طلبات",
)

_EN_DATA_RE = re.compile(
    r"\b("
    r"count|how\s+many|list|lists|show|sales|order|orders|customer|customers|"
    r"top|bottom|best|worst|lowest|highest|total|sum|average|avg|revenue|"
    r"quantity|amount"
    r")\b",
    re.IGNORECASE,
)


class ChatPath(StrEnum):
    """High-level routing decision for ``/api/v1/chat``."""

    SQL_FAST = "sql_fast"
    VANNA_AGENT = "vanna_agent"


def _has_arabic_data_intent(text: str) -> bool:
    return any(tok in text for tok in _AR_DATA_TOKENS)


def _has_english_data_intent(text: str) -> bool:
    return _EN_DATA_RE.search(text) is not None


_COMPLEX_HINTS: frozenset[str] = frozenset({
    "مع",
    "بين",
    "لكل",
    "حسب",
    "توزيع",
    "مقارنة",
    "compare",
    "versus",
    "vs",
    "breakdown",
    "distribution",
    "per",
    "across",
    "correlation",
})


def needs_enhanced_context(question: str) -> bool:
    """Return True when the question likely needs richer context (joins, business rules)."""

    q = question.strip().lower()
    return any(hint in q for hint in _COMPLEX_HINTS)


def route_intent(question: str) -> ChatPath:
    """Return :class:`ChatPath.SQL_FAST` when the question clearly asks for tabular data."""

    q = question.strip()
    if not q:
        return ChatPath.VANNA_AGENT

    if _has_arabic_data_intent(q) or _has_english_data_intent(q):
        return ChatPath.SQL_FAST
    return ChatPath.VANNA_AGENT
