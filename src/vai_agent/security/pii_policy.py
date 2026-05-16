"""PII and sensitive-column policy engine.

Checks a SQL string against the column-level sensitivity lists in a
:class:`~vai_agent.knowledge.profile_models.SecurityPolicy` and applies
a name-heuristic scan for columns that are not in the profile but whose
names suggest personally-identifiable or secret information.

Violation codes
---------------
PII001  Secret column referenced (always an error — blocks execution)
PII002  PII column referenced (error by default — blocks execution)
PII003  Sensitive column referenced (error by default — blocks execution)
PII004  Column name matches a PII heuristic pattern (warning — does not block)

Design notes
------------
Column matching uses three tiers:

1. **Exact qualified match**: ``Table.Column`` extracted from the policy
   list is compared against a fully-qualified ``table.column`` reference
   in the SQL (e.g. ``Customers.ContactName``).

2. **Column-only match** (conservative): if the SQL reference has no
   table qualifier (e.g. ``SELECT ContactName …``), we check whether
   *any* policy entry with that column name is flagged. This may produce
   false positives when the same column name exists in both sensitive and
   non-sensitive tables, but false positives are preferred over false
   negatives for security.

3. **Heuristic match**: column names that are not in the policy but whose
   lowercase form matches known PII/secret patterns (phone, email, ssn,
   password, …) are flagged as PII004 warnings. These are informational
   and do **not** block execution.

Access-group logic
------------------
* **secret** columns: only ``admin`` may reference them.
* **sensitive** columns: ``admin`` or ``security``.
* **pii** columns: ``admin`` or ``pii_reader``.
* Other callers receive blocking violations (severity ``error``) when the column
  matches a policy tier. Heuristic PII004 warnings are unchanged.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

import sqlglot
import sqlglot.errors
import sqlglot.expressions as exp
from pydantic import BaseModel, ConfigDict, Field

from vai_agent.knowledge.profile_models import SecurityPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Violation / result models
# ---------------------------------------------------------------------------


class PiiViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["error", "warning"]
    column_ref: str
    message: str


class PiiCheckResult(BaseModel):
    allowed: bool
    violations: list[PiiViolation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

# Columns whose names *contain* any of these tokens are flagged as PII.
# Applied after lowercasing and removing underscores/hyphens.
_HEURISTIC_PII_TOKENS: frozenset[str] = frozenset({
    "email", "phone", "mobile", "fax", "address", "street",
    "zipcode", "postalcode", "birthdate", "dateofbirth", "dob",
    "firstname", "lastname", "fullname", "nationalid", "passport",
    "ipaddress", "deviceid",
})

# Column name tokens that suggest *secret* data (stricter than PII).
_HEURISTIC_SECRET_TOKENS: frozenset[str] = frozenset({
    "password", "passwd", "pwd", "secret", "token", "apikey",
    "privatekey", "creditcard", "cardnumber", "cvv", "ssn",
    "socialsecurity",
})


def _heuristic_category(col_name: str) -> Literal["secret", "pii", "none"]:
    """Classify a column name using name heuristics only."""
    normalised = re.sub(r"[_\-\s]", "", col_name.lower())
    if any(t in normalised for t in _HEURISTIC_SECRET_TOKENS):
        return "secret"
    if any(t in normalised for t in _HEURISTIC_PII_TOKENS):
        return "pii"
    return "none"


# ---------------------------------------------------------------------------
# Lookup builder
# ---------------------------------------------------------------------------


def _build_lookup(
    entries: list[str],
) -> tuple[dict[str, str], set[str]]:
    """Build lookup structures from a ``Table.Column`` or ``Column`` list.

    Returns
    -------
    qualified : dict[str, str]
        Mapping ``"table.column"`` (lowercase) → original entry string.
    col_only : set[str]
        Just the column names (lowercase) so that unqualified references
        can be caught conservatively.
    """
    qualified: dict[str, str] = {}
    col_only: set[str] = set()
    for entry in entries:
        entry_lower = entry.lower()
        if "." in entry_lower:
            qualified[entry_lower] = entry
            col_name = entry_lower.split(".", 1)[1]
            col_only.add(col_name)
        else:
            col_only.add(entry_lower)
    return qualified, col_only


# ---------------------------------------------------------------------------
# Column-reference extraction from SQL
# ---------------------------------------------------------------------------


def _extract_column_refs(sql: str) -> list[tuple[str | None, str]]:
    """Return ``(table_or_alias, column_name)`` pairs from the SQL AST.

    ``table_or_alias`` is ``None`` when the column has no qualifier.
    Returns an empty list when the SQL cannot be parsed.
    """
    try:
        stmts = sqlglot.parse(
            sql, read="tsql", error_level=sqlglot.errors.ErrorLevel.WARN,
        )
    except Exception:
        return []

    refs: list[tuple[str | None, str]] = []
    for stmt in stmts:
        if stmt is None:
            continue
        for col in stmt.find_all(exp.Column):
            table_ref: str | None = col.table if col.table else None
            refs.append((table_ref, col.name))
    return refs


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------


class PiiPolicyEngine:
    """Check SQL column references against the sensitivity lists in a policy.

    Parameters
    ----------
    policy:
        The :class:`~vai_agent.knowledge.profile_models.SecurityPolicy`
        whose ``pii_columns``, ``sensitive_columns``, and ``secret_columns``
        lists are enforced.
    """

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy
        self._secret_q, self._secret_col = _build_lookup(policy.secret_columns)
        self._pii_q, self._pii_col = _build_lookup(policy.pii_columns)
        self._sensitive_q, self._sensitive_col = _build_lookup(policy.sensitive_columns)

    def check(
        self,
        sql: str,
        *,
        user_groups: list[str] | None = None,  # reserved for Phase 5
    ) -> PiiCheckResult:
        """Return a :class:`PiiCheckResult` for *sql*.

        This method never executes SQL. It is safe to call before the SQL
        policy engine's structural checks, but callers typically run
        :class:`SqlPolicyEngine` first to ensure the SQL is well-formed.
        """
        violations: list[PiiViolation] = []
        seen_refs: set[str] = set()  # deduplicate identical column refs

        refs = _extract_column_refs(sql)
        for table_ref, col_name in refs:
            ref_key = f"{table_ref}.{col_name}".lower() if table_ref else col_name.lower()
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)

            violations.extend(self._check_ref(table_ref, col_name, user_groups=user_groups))

        # Apply heuristics to column names not already flagged from the
        # policy lists.
        policy_flagged_cols = (
            self._secret_col | self._pii_col | self._sensitive_col
        )
        for table_ref, col_name in refs:
            if col_name.lower() in policy_flagged_cols:
                continue  # already handled by policy check above
            category = _heuristic_category(col_name)
            if category == "none":
                continue
            ref_display = f"{table_ref}.{col_name}" if table_ref else col_name
            heuristic_key = f"heuristic:{ref_display.lower()}"
            if heuristic_key in seen_refs:
                continue
            seen_refs.add(heuristic_key)
            violations.append(PiiViolation(
                code="PII004",
                severity="warning",
                column_ref=ref_display,
                message=(
                    f"Column '{ref_display}' matches a PII name pattern "
                    f"and may contain sensitive data. Add it to the "
                    f"security policy if it should be blocked."
                ),
            ))

        has_errors = any(v.severity == "error" for v in violations)
        return PiiCheckResult(allowed=not has_errors, violations=violations)

    def _check_ref(
        self,
        table_ref: str | None,
        col_name: str,
        *,
        user_groups: list[str] | None = None,
    ) -> list[PiiViolation]:
        """Return violations for a single column reference."""
        col_lower = col_name.lower()
        table_lower = table_ref.lower() if table_ref else None
        qualified_key = f"{table_lower}.{col_lower}" if table_lower else None
        display = f"{table_ref}.{col_name}" if table_ref else col_name

        violations: list[PiiViolation] = []
        groups = set(user_groups or [])

        # --- Secret columns (highest severity) ----------------------------- #
        if (qualified_key and qualified_key in self._secret_q) or col_lower in self._secret_col:
            if "admin" in groups:
                return []
            violations.append(PiiViolation(
                code="PII001",
                severity="error",
                column_ref=display,
                message=f"Column '{display}' is classified as secret and cannot be queried.",
            ))
            return violations

        # --- PII columns ---------------------------------------------------- #
        if (qualified_key and qualified_key in self._pii_q) or col_lower in self._pii_col:
            if groups & {"admin", "pii_reader"}:
                return []
            violations.append(PiiViolation(
                code="PII002",
                severity="error",
                column_ref=display,
                message=f"Column '{display}' contains personally-identifiable information.",
            ))
            return violations

        # --- Sensitive columns ----------------------------------------------- #
        if (
            (qualified_key and qualified_key in self._sensitive_q)
            or col_lower in self._sensitive_col
        ):
            if groups & {"admin", "security"}:
                return []
            violations.append(PiiViolation(
                code="PII003",
                severity="error",
                column_ref=display,
                message=f"Column '{display}' is classified as sensitive.",
            ))
            return violations

        return violations


def can_access_sensitive_column(
    *,
    column_name: str,
    table_name: str,
    user_groups: list[str],
    policy: SecurityPolicy,
) -> bool:
    """Return True if *user_groups* may reference *column_name* on *table_name* per *policy* tiers."""

    engine = PiiPolicyEngine(policy)
    return not bool(
        engine._check_ref(
            table_name if table_name else None,
            column_name,
            user_groups=user_groups,
        ),
    )
