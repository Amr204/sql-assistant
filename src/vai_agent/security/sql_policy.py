"""SQL policy engine: validates a SQL string before it reaches the database.

This module provides *pure validation* — no SQL is executed. The caller
is responsible for deciding what to do with the result (reject, log,
rewrite, pass to the runner). The only transformation performed here is
injecting a ``TOP N`` clause when the query does not already have one.

Violation codes
---------------
POL001  Non-SELECT statement (DML / DDL / EXEC blocked)
POL002  Multiple statements in a single call
POL003  SELECT * — wildcard column selection forbidden
POL004  Blocked schema reference (sys, INFORMATION_SCHEMA, …)
POL005  Blocked function or stored procedure (OPENROWSET, xp_cmdshell, …)
POL006  Cross-database reference (three-part or four-part table name)
POL007  Blocked table (explicit table deny-list in policy)
POL008  SELECT INTO — creates a table, not permitted
POL009  Empty or unparseable query
POL010  Injection-pattern detected in query text
POL011  Table uses a schema outside the allow-list
POL012  Table is outside the allowed table list
POL013  Required row-filter predicate missing
POL014  Blocked SQL feature token detected

Design notes
------------
* All checks run on every call even after errors are found, so callers
  receive the full violation list in one pass.
* Checks use sqlglot's T-SQL AST as the primary mechanism, supplemented
  by regex for patterns that sqlglot 30.x does not surface structurally
  (e.g. comment-embedded keywords, dangerous function names).
* User-facing messages are intentionally vague to avoid leaking internal
  schema information to potential attackers.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal

import sqlglot
import sqlglot.errors
import sqlglot.expressions as exp
from pydantic import BaseModel, ConfigDict, Field

from vai_agent.knowledge.profile_models import RowFilter

if TYPE_CHECKING:
    from vai_agent.knowledge.profile_models import SecurityPolicy

logger = logging.getLogger(__name__)


class PolicyViolation(BaseModel):
    """A single policy check result."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["error", "warning"]
    message: str


class SqlPolicyResult(BaseModel):
    """Return value of :meth:`SqlPolicyEngine.validate`."""

    allowed: bool
    violations: list[PolicyViolation] = Field(default_factory=list)
    rewritten_sql: str | None = Field(
        default=None,
        description=(
            "The SQL ready for execution. Populated only when ``allowed`` is "
            "``True``. May differ from the original when a TOP clause was added."
        ),
    )


# ---------------------------------------------------------------------------
# Row-level filter validation (conservative; WHERE AST + predicate text)
# ---------------------------------------------------------------------------


def _where_predicate_sql(stmt: exp.Expression) -> str | None:
    """Lowercased T-SQL text of the main SELECT ``WHERE`` condition only."""

    if isinstance(stmt, exp.Union):
        return None
    if not isinstance(stmt, exp.Select):
        return None
    w = stmt.args.get("where")
    if w is None:
        return None
    try:
        inner = getattr(w, "this", w)
        return inner.sql(dialect="tsql").lower()
    except Exception:
        return None


def row_filter_violations(
    stmt: exp.Expression,
    row_filters: list[RowFilter],
    user_groups: list[str] | None,
) -> list[PolicyViolation]:
    """Return POL013 violations when a required predicate cannot be proven in ``WHERE``."""

    violations: list[PolicyViolation] = []
    for rf in row_filters:
        if rf.applies_to_groups and not any(g in (user_groups or []) for g in rf.applies_to_groups):
            continue
        table_referenced = any(
            t.name.lower() == rf.table.lower() for t in stmt.find_all(exp.Table)
        )
        if not table_referenced:
            continue

        if isinstance(stmt, exp.Union):
            violations.append(PolicyViolation(
                code="POL013",
                severity="error",
                message="Required row filter cannot be proven on UNION queries.",
            ))
            continue

        where_sql = _where_predicate_sql(stmt)
        expr_norm = " ".join(rf.expression.lower().split())

        if where_sql is None:
            violations.append(PolicyViolation(
                code="POL013",
                severity="error",
                message="Query does not include a required row-level filter predicate.",
            ))
            continue

        if expr_norm not in where_sql:
            violations.append(PolicyViolation(
                code="POL013",
                severity="error",
                message="Query does not include a required row-level filter predicate in the WHERE clause.",
            ))

    return violations


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Statements that must never be executed regardless of policy.
_BLOCKED_STATEMENT_TYPES = (
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Execute,  # EXEC / EXECUTE
    exp.Grant,
    exp.Revoke,
    exp.Transaction,
)

# Schemas that are always blocked (belt-and-suspenders alongside the policy list).
_ALWAYS_BLOCKED_SCHEMAS: frozenset[str] = frozenset({
    "sys", "information_schema",
})

# Functions and procedures that are always blocked regardless of policy.
_ALWAYS_BLOCKED_FUNCTIONS: frozenset[str] = frozenset({
    "openrowset", "openquery", "opendatasource",
    "xp_cmdshell", "xp_regread", "xp_regwrite", "xp_fileexist",
    "xp_dirtree", "xp_ntsec_enumdomains", "xp_logininfo",
    "xp_msver", "xp_fixeddrives",
    "sp_oacreate", "sp_oamethod", "sp_oagetproperty",
    "sp_executesql",  # can be used for dynamic SQL injection
})

# Regex patterns that hint at prompt-injection attempts.
# These are heuristic, not exhaustive.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(previous\s+)?instructions?\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(all\s+)?(previous\s+)?(instructions?|rules?)\b", re.IGNORECASE),
    re.compile(r"\bnow\s+(you\s+are|act\s+as)\b", re.IGNORECASE),
    re.compile(r"\bOR\s+1\s*=\s*1\b", re.IGNORECASE),
    re.compile(r"\bOR\s+'[^']+'\s*=\s*'[^']+'\b", re.IGNORECASE),
]

# Regex to catch dangerous function names that AST parsing might miss
# (e.g. inside a comment or as a procedure name in unusual EXEC forms).
_DANGEROUS_FUNC_RE = re.compile(
    r"\b(OPENROWSET|OPENQUERY|OPENDATASOURCE|xp_cmdshell|xp_\w+|sp_oacreate|sp_oamethod)\b",
    re.IGNORECASE,
)

# Regex: semicolon that is NOT at the very end of the trimmed statement.
_MID_SEMICOLON_RE = re.compile(r";(?!\s*$)")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _first_keyword(sql: str) -> str:
    """Return the first non-comment, non-whitespace keyword in ``sql``."""
    # Strip leading line comments (-- ...) and block comments (/* ... */)
    stripped = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    tokens = stripped.split()
    return tokens[0].upper().rstrip(";") if tokens else ""


def _collect_function_names(stmt: exp.Expression) -> set[str]:
    """Walk the AST and return lowercase names of all function calls."""
    names: set[str] = set()
    for node in stmt.walk():
        if isinstance(node, exp.Anonymous):
            names.add(node.name.lower())
    return names


def _star_allowed(node: exp.Star) -> bool:
    parent = node.parent
    return isinstance(parent, exp.Count)


def _table_db_name(tbl: exp.Table) -> str:
    """Return the schema/qualifier db-part of a table reference, lowercased."""
    db_arg = tbl.args.get("db")
    if db_arg is None:
        return ""
    return db_arg.name.lower() if hasattr(db_arg, "name") else str(db_arg).lower()


def _table_catalog_name(tbl: exp.Table) -> str:
    """Return the database/catalog part of a three-or-four-part name."""
    cat_arg = tbl.args.get("catalog")
    if cat_arg is None:
        return ""
    return cat_arg.name if hasattr(cat_arg, "name") else str(cat_arg)


def _has_limit(stmt: exp.Expression) -> bool:
    """True when the statement already has a TOP / LIMIT clause."""
    return stmt.args.get("limit") is not None


def _inject_top(stmt: exp.Expression, original_sql: str, max_rows: int) -> str:
    """Return ``original_sql`` with ``TOP max_rows`` appended after SELECT.

    Skips injection for:
    * CTEs  (``WITH … SELECT …``) — CTE subqueries would receive the wrong TOP
    * UNIONs — ambiguous which side to limit
    * Statements that already carry a TOP/LIMIT

    In those cases the original SQL is returned unchanged (the runner should
    apply a separate row cap at the connection level).
    """
    if not isinstance(stmt, exp.Select):
        return original_sql
    if stmt.args.get("with_"):  # CTE
        return original_sql
    if _has_limit(stmt):
        return original_sql

    # Find the position of the leading SELECT keyword (after any comments/
    # whitespace) and insert TOP N immediately after it.
    m = re.search(r"\bSELECT\b", original_sql, re.IGNORECASE)
    if m is None:
        return original_sql
    pos = m.end()
    return original_sql[:pos] + f" TOP {max_rows}" + original_sql[pos:]


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------


class SqlPolicyEngine:
    """Validate a SQL string against a :class:`SecurityPolicy`.

    Parameters
    ----------
    policy:
        The security policy to enforce. Can be obtained from a loaded
        :class:`~vai_agent.knowledge.profile_models.Profile` via
        ``profile.security_policy``.
    """

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy
        # Pre-build lowercase lookup sets from policy
        self._blocked_schemas_lower: frozenset[str] = (
            _ALWAYS_BLOCKED_SCHEMAS
            | frozenset(s.lower() for s in policy.blocked_schemas)
        )
        self._blocked_tables_lower: frozenset[str] = frozenset(
            t.lower() for t in policy.blocked_tables
        )
        self._allowed_tables_lower: frozenset[str] = frozenset(
            t.lower() for t in policy.allowed_tables
        )
        self._allowed_schemas_lower: frozenset[str] = frozenset(
            s.lower() for s in policy.allowed_schemas
        )
        self._blocked_funcs_lower: frozenset[str] = (
            _ALWAYS_BLOCKED_FUNCTIONS
            | frozenset(f.lower() for f in policy.blocked_functions)
        )
        self._blocked_features_lower: frozenset[str] = frozenset(
            f.lower() for f in policy.blocked_sql_features
        )

    def validate(
        self,
        sql: str,
        *,
        user_groups: list[str] | None = None,  # reserved for Phase 5 access-group checks
    ) -> SqlPolicyResult:
        """Validate *sql* and return a :class:`SqlPolicyResult`.

        This method **never executes SQL**. All violations are collected
        before returning so the caller sees the full picture.
        """
        violations: list[PolicyViolation] = []

        # ------------------------------------------------------------------ #
        # 1. Empty input                                                       #
        # ------------------------------------------------------------------ #
        sql_stripped = sql.strip()
        if not sql_stripped:
            return SqlPolicyResult(
                allowed=False,
                violations=[
                    PolicyViolation(code="POL009", severity="error", message="Query is empty."),
                ],
            )

        # ------------------------------------------------------------------ #
        # 2. Injection pattern heuristics (before parsing)                    #
        # ------------------------------------------------------------------ #
        for pat in _INJECTION_PATTERNS:
            if pat.search(sql_stripped):
                violations.append(PolicyViolation(
                    code="POL010",
                    severity="error",
                    message="Query contains patterns associated with injection attacks.",
                ))
                break

        # ------------------------------------------------------------------ #
        # 3. Multiple statements — fast semicolon check                       #
        # ------------------------------------------------------------------ #
        if _MID_SEMICOLON_RE.search(sql_stripped):
            violations.append(PolicyViolation(
                code="POL002",
                severity="error",
                message="Multiple SQL statements in a single query are not allowed.",
            ))

        # ------------------------------------------------------------------ #
        # 4. First-keyword check (before AST parse, belt-and-suspenders)     #
        # ------------------------------------------------------------------ #
        first_kw = _first_keyword(sql_stripped)
        _BLOCKED_KWS = {
            "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER",
            "CREATE", "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE",
            "DENY", "BACKUP", "RESTORE", "BULK", "KILL", "SHUTDOWN",
        }
        if first_kw in _BLOCKED_KWS:
            violations.append(PolicyViolation(
                code="POL001",
                severity="error",
                message="Only SELECT statements are permitted.",
            ))

        # ------------------------------------------------------------------ #
        # 5. Dangerous functions — regex (belt-and-suspenders)               #
        # ------------------------------------------------------------------ #
        if _DANGEROUS_FUNC_RE.search(sql_stripped):
            violations.append(PolicyViolation(
                code="POL005",
                severity="error",
                message="Query references a blocked function or stored procedure.",
            ))

        # Bail early if we already have blocking errors — avoid expensive parse
        if any(v.severity == "error" for v in violations):
            return SqlPolicyResult(allowed=False, violations=violations)

        # ------------------------------------------------------------------ #
        # 6. Parse with sqlglot (T-SQL dialect)                               #
        # ------------------------------------------------------------------ #
        try:
            statements = sqlglot.parse(
                sql_stripped,
                read="tsql",
                error_level=sqlglot.errors.ErrorLevel.WARN,
            )
        except Exception:
            logger.debug("sqlglot parse error for query (blocked)", exc_info=False)
            return SqlPolicyResult(
                allowed=False,
                violations=[PolicyViolation(
                    code="POL009",
                    severity="error",
                    message="Query could not be parsed. Check syntax.",
                )],
            )

        statements = [s for s in statements if s is not None]

        if not statements:
            return SqlPolicyResult(
                allowed=False,
                violations=[PolicyViolation(
                    code="POL009",
                    severity="error",
                    message="No valid SQL statement found.",
                )],
            )

        # ------------------------------------------------------------------ #
        # 7. Multiple statements in AST                                        #
        # ------------------------------------------------------------------ #
        if len(statements) > 1:
            violations.append(PolicyViolation(
                code="POL002",
                severity="error",
                message="Multiple SQL statements in a single query are not allowed.",
            ))
            return SqlPolicyResult(allowed=False, violations=violations)

        stmt = statements[0]

        # ------------------------------------------------------------------ #
        # 8. Statement type (DML / DDL / EXEC)                                #
        # ------------------------------------------------------------------ #
        if isinstance(stmt, _BLOCKED_STATEMENT_TYPES):
            violations.append(PolicyViolation(
                code="POL001",
                severity="error",
                message="Only SELECT statements are permitted.",
            ))
        elif not isinstance(stmt, (exp.Select, exp.Union)):
            # Catch anything else that is not a query
            violations.append(PolicyViolation(
                code="POL001",
                severity="error",
                message="Only SELECT statements are permitted.",
            ))

        # ------------------------------------------------------------------ #
        # 9. SELECT INTO                                                       #
        # ------------------------------------------------------------------ #
        if stmt.find(exp.Into) is not None:
            violations.append(PolicyViolation(
                code="POL008",
                severity="error",
                message="SELECT INTO is not permitted.",
            ))

        # ------------------------------------------------------------------ #
        # 10. SELECT *                                                         #
        # ------------------------------------------------------------------ #
        if any(not _star_allowed(star) for star in stmt.find_all(exp.Star)):
            violations.append(PolicyViolation(
                code="POL003",
                severity="error",
                message="SELECT * is not allowed. Specify column names explicitly.",
            ))

        # ------------------------------------------------------------------ #
        # 11. Blocked schemas (AST)                                           #
        # ------------------------------------------------------------------ #
        for tbl in stmt.find_all(exp.Table):
            if _table_db_name(tbl) in self._blocked_schemas_lower:
                violations.append(PolicyViolation(
                    code="POL004",
                    severity="error",
                    message="Query references a blocked schema.",
                ))
                break

        # Belt-and-suspenders: regex for INFORMATION_SCHEMA and sys
        if re.search(r"\b(INFORMATION_SCHEMA|sys)\b", sql_stripped, re.IGNORECASE) and not any(
            v.code == "POL004" for v in violations
        ):
            violations.append(PolicyViolation(
                code="POL004",
                severity="error",
                message="Query references a blocked schema.",
            ))

        # ------------------------------------------------------------------ #
        # 12. Blocked functions (AST + regex already ran above)               #
        # ------------------------------------------------------------------ #
        ast_funcs = _collect_function_names(stmt)
        if ast_funcs & self._blocked_funcs_lower and not any(v.code == "POL005" for v in violations):
            violations.append(PolicyViolation(
                code="POL005",
                severity="error",
                message="Query references a blocked function or stored procedure.",
            ))

        # ------------------------------------------------------------------ #
        # 13. Cross-database reference                                         #
        # ------------------------------------------------------------------ #
        for tbl in stmt.find_all(exp.Table):
            if _table_catalog_name(tbl):
                violations.append(PolicyViolation(
                    code="POL006",
                    severity="error",
                    message="Cross-database queries are not allowed.",
                ))
                break

        # ------------------------------------------------------------------ #
        # 14. Blocked tables                                                   #
        # ------------------------------------------------------------------ #
        if self._blocked_tables_lower:
            for tbl in stmt.find_all(exp.Table):
                if tbl.name.lower() in self._blocked_tables_lower:
                    violations.append(PolicyViolation(
                        code="POL007",
                        severity="error",
                        message="Query references a table that is not accessible.",
                    ))
                    break

        # ------------------------------------------------------------------ #
        # 15. Allowed schemas / tables                                        #
        # ------------------------------------------------------------------ #
        if self._allowed_schemas_lower:
            for tbl in stmt.find_all(exp.Table):
                schema_name = _table_db_name(tbl)
                if schema_name and schema_name not in self._allowed_schemas_lower:
                    violations.append(PolicyViolation(
                        code="POL011",
                        severity="error",
                        message="Query references a schema outside the allowed set.",
                    ))
                    break
        if self._allowed_tables_lower:
            for tbl in stmt.find_all(exp.Table):
                if tbl.name.lower() not in self._allowed_tables_lower:
                    violations.append(PolicyViolation(
                        code="POL012",
                        severity="error",
                        message="Query references a table outside the allowed set.",
                    ))
                    break

        # ------------------------------------------------------------------ #
        # 16. Blocked SQL features                                            #
        # ------------------------------------------------------------------ #
        for feature in self._blocked_features_lower:
            if re.search(rf"\b{re.escape(feature)}\b", sql_stripped, re.IGNORECASE):
                violations.append(PolicyViolation(
                    code="POL014",
                    severity="error",
                    message="Query contains a blocked SQL feature.",
                ))
                break

        # ------------------------------------------------------------------ #
        # 17. Row filters (WHERE AST — conservative; no automatic SQL rewrite)
        # ------------------------------------------------------------------ #
        violations.extend(
            row_filter_violations(
                stmt,
                self._policy.row_filters,
                user_groups,
            ),
        )

        # ------------------------------------------------------------------ #
        # Determine outcome                                                    #
        # ------------------------------------------------------------------ #
        if any(v.severity == "error" for v in violations):
            return SqlPolicyResult(allowed=False, violations=violations)

        rewritten = _inject_top(stmt, sql_stripped, self._policy.max_rows)
        return SqlPolicyResult(
            allowed=True,
            violations=violations,
            rewritten_sql=rewritten,
        )
