"""Post-process generated SQL before execution (SQL Server alias safety)."""

from __future__ import annotations

import re

_FORBIDDEN_COUNT_ALIASES = (
    r"\bAS\s+RowCount\b",
    r"\bAS\s+rowcount\b",
    r"\bAS\s+ROWCOUNT\b",
    r"\bAS\s+\[RowCount\]",
    r"\bAS\s+\[rowcount\]",
    r"\bAS\s+\[ROWCOUNT\]",
)


def normalize_sql_aliases(sql: str) -> str:
    """Replace forbidden ``RowCount`` column aliases with ``[record_count]``."""

    normalized = sql
    for pattern in _FORBIDDEN_COUNT_ALIASES:
        normalized = re.sub(pattern, "AS [record_count]", normalized, flags=re.IGNORECASE)
    return normalized
