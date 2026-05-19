"""Security layer: SQL policy validation and PII column protection.

Phase 4 deliverables. No SQL is executed here; these modules are pure
validators that the execution layer (policy-gated SQL runners)
will call before touching the database.

Usage example::

    from vai_agent.security import SqlPolicyEngine, PiiPolicyEngine
    from vai_agent.knowledge import ProfileLoader

    profile = ProfileLoader("profiles").load("dbnwind")
    sql_engine = SqlPolicyEngine(profile.security_policy)
    pii_engine = PiiPolicyEngine(profile.security_policy)

    sql_result = sql_engine.validate(user_sql)
    if not sql_result.allowed:
        raise SqlPolicyViolationError(sql_result)

    pii_result = pii_engine.check(user_sql)
    if not pii_result.allowed:
        raise PiiViolationError(pii_result)

    # sql_result.rewritten_sql is safe to hand to the runner
"""

from vai_agent.security.errors import PiiViolationError, SecurityError, SqlPolicyViolationError
from vai_agent.security.pii_policy import PiiCheckResult, PiiPolicyEngine, PiiViolation
from vai_agent.security.sql_policy import PolicyViolation, SqlPolicyEngine, SqlPolicyResult

__all__ = [
    "PiiCheckResult",
    "PiiPolicyEngine",
    "PiiViolation",
    "PiiViolationError",
    "PolicyViolation",
    "SecurityError",
    "SqlPolicyEngine",
    "SqlPolicyResult",
    "SqlPolicyViolationError",
]
