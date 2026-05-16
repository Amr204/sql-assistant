"""Security exception hierarchy.

The policy engines (``SqlPolicyEngine``, ``PiiPolicyEngine``) return
result objects rather than raising by default, so callers can inspect
every violation at once. These exceptions exist for callers that
prefer raise-on-block semantics (e.g. integration tests, strict mode).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vai_agent.security.pii_policy import PiiCheckResult
    from vai_agent.security.sql_policy import SqlPolicyResult


class SecurityError(Exception):
    """Base class for all SQL Assistant security errors."""


class SqlPolicyViolationError(SecurityError):
    """Raised when a query is blocked by the SQL policy engine.

    Parameters
    ----------
    result:
        The full :class:`~vai_agent.security.sql_policy.SqlPolicyResult`
        that led to the block. Inspect ``result.violations`` for details.
    """

    def __init__(self, result: SqlPolicyResult) -> None:
        self.result = result
        first = result.violations[0].message if result.violations else "unknown reason"
        super().__init__(f"SQL blocked ({len(result.violations)} violation(s)): {first}")


class PiiViolationError(SecurityError):
    """Raised when a query is blocked due to PII / sensitive-column access.

    Parameters
    ----------
    result:
        The full :class:`~vai_agent.security.pii_policy.PiiCheckResult`
        that led to the block.
    """

    def __init__(self, result: PiiCheckResult) -> None:
        self.result = result
        n = len([v for v in result.violations if v.severity == "error"])
        super().__init__(f"Query blocked: {n} sensitive column(s) referenced.")
