"""Post-query masking and coarse aggregation privacy checks.

``masking_rules`` and ``min_group_size`` from :class:`~vai_agent.knowledge.profile_models.SecurityPolicy`
are applied to tabular result rows **after** SQL validation and execution.

``min_group_size`` enforcement here is **basic**: it only filters rows when integer
count-like columns fall below the threshold. It is **not** a formal differential
privacy guarantee.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from vai_agent.knowledge.profile_models import MaskingRule, MaskType


def _norm_key(name: str) -> str:
    return name.strip().lower()


def _rule_matches_column(rule_column: str, row_key: str) -> bool:
    rc = _norm_key(rule_column)
    rk = _norm_key(row_key)
    if rc == rk:
        return True
    if "." in rc and rc.split(".")[-1] == rk:
        return True
    return rc.endswith(f".{rk}")


def apply_masking_rules(
    rows: list[dict[str, Any]],
    *,
    masking_rules: list[MaskingRule],
    user_groups: list[str],
) -> list[dict[str, Any]]:
    """Apply profile masking rules to result rows (admins see raw values)."""

    if "admin" in set(user_groups or []):
        return rows

    if not masking_rules:
        return rows

    ug = set(user_groups or [])
    masked_rows: list[dict[str, Any]] = []

    for row in rows:
        clean = dict(row)
        for rule in masking_rules:
            if rule.applies_to_groups and not (ug & set(rule.applies_to_groups)):
                continue
            col_key = next(
                (k for k in clean if _rule_matches_column(rule.column, k)),
                None,
            )
            if col_key is None:
                continue
            value = clean[col_key]
            if value is None:
                continue

            if rule.mask_type in (MaskType.redact,):
                clean[col_key] = "[REDACTED]"
            elif rule.mask_type is MaskType.partial:
                text = str(value)
                if "@" in text and re.search(r"\S+@\S+", text):
                    name, _, domain = text.partition("@")
                    clean[col_key] = f"{name[:1]}***@{domain}" if name else "***"
                else:
                    clean[col_key] = "***"
            elif rule.mask_type is MaskType.hash:
                h = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
                clean[col_key] = f"[HASH:{h}]"
            else:
                clean[col_key] = "[MASKED]"

        masked_rows.append(clean)

    return masked_rows


def enforce_min_group_size(
    rows: list[dict[str, Any]],
    *,
    min_group_size: int,
    user_groups: list[str],
) -> list[dict[str, Any]]:
    """Drop rows whose count-like columns fall below ``min_group_size`` (non-admins)."""

    if "admin" in set(user_groups or []):
        return rows

    if min_group_size <= 1:
        return rows

    count_keys = frozenset({"count", "cnt", "total_count", "row_count", "n"})
    filtered: list[dict[str, Any]] = []

    for row in rows:
        counts = [
            int(value)
            for key, value in row.items()
            if str(key).lower() in count_keys and isinstance(value, (int, float))
        ]
        if counts and any(c < min_group_size for c in counts):
            continue
        filtered.append(row)

    return filtered
