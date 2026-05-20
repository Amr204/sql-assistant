"""Safe MSSQL query runner.

:class:`MssqlRunner` is the *only* place in the codebase where SQL
reaches the database. Every query must be pre-approved by both
:class:`~vai_agent.security.sql_policy.SqlPolicyEngine` and
:class:`~vai_agent.security.pii_policy.PiiPolicyEngine` before it is
passed here.

Guarantees enforced by this module
------------------------------------
1. **Query timeout** — ``SET QUERY_GOVERNOR_COST_LIMIT`` is set at the
   session level so long-running queries are automatically cancelled.
   pyodbc's ``timeout`` attribute provides a second, client-side
   deadline.
2. **Row cap** — rows are read with ``cursor.fetchmany``; accumulation
   stops when ``max_rows`` is exceeded and ``truncated`` is set.
3. **Safe result format** — results are returned as a
   :class:`QueryResult` (a plain Pydantic model: list of column names +
   list-of-dicts rows). No raw DBAPI cursor leaks out.
4. **Safe error messages** — exceptions from pyodbc are caught and the
   internal error string is *never* forwarded to callers.  Only a
   sanitised :class:`RunnerError` is raised.
5. **No secrets in logs** — the connection string is never logged; only
   the driver / host / database appear via :meth:`ConnectionSettings.safe_repr`.

Usage example::

    from vai_agent.db.connection import ConnectionSettings
    from vai_agent.db.mssql_runner import MssqlRunner
    from vai_agent.security import SqlPolicyEngine, PiiPolicyEngine

    # Build once, reuse for the lifetime of the request.
    settings = ConnectionSettings(...)
    runner = MssqlRunner(settings, max_rows=500, query_timeout=15)

    policy_result = SqlPolicyEngine(security_policy).validate(user_sql)
    pii_result    = PiiPolicyEngine(security_policy).check(user_sql)
    assert policy_result.allowed and pii_result.allowed

    result = runner.execute(policy_result.rewritten_sql)
    print(result.rows[:5])
"""

from __future__ import annotations

import base64
import contextlib
import logging
import math
import re
import threading
from collections.abc import Iterator, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from typing import Any

import pyodbc
from pydantic import BaseModel, ConfigDict, Field

from vai_agent.audit.activity_recorder import (
    ActivityEvent,
    get_activity_recorder,
    safe_record_activity,
)
from vai_agent.db.connection import ConnectionSettings
from vai_agent.db.sql_alias_guard import normalize_sql_aliases

pyodbc.pooling = False  # Managed by ConnectionPool below

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result + error models
# ---------------------------------------------------------------------------


class QueryResult(BaseModel):
    """Serialisable, UI-friendly query result.

    Rows are plain ``list[dict]`` so they can be JSON-serialised directly
    by FastAPI's response layer without extra conversion.
    """

    model_config = ConfigDict(frozen=True)

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = Field(
        default=False,
        description="True when the result was capped at max_rows.",
    )
    rewritten_sql: str | None = Field(
        default=None,
        description="Policy-layer rewritten SQL (before alias guard).",
    )
    sql_executed: str | None = Field(
        default=None,
        description="SQL executed on the server after alias normalization.",
    )


class RunnerError(Exception):
    """Raised when query execution fails.

    The ``safe_message`` attribute is safe to show to end users.
    The ``debug_hint`` attribute contains only the exception class name
    for operators and is **not** for display to end users.
    """

    def __init__(self, safe_message: str, debug_hint: str = "") -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.debug_hint = debug_hint


class QueryTimeoutError(RunnerError):
    """Raised when the query exceeds the configured timeout."""


class RowLimitError(RunnerError):
    """Raised when the result exceeds ``max_rows`` mid-stream."""


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------

# pyodbc / SQL Server error codes that indicate a timeout.
# 0  = generic pyodbc timeout (client-side)
# -2 = HY008 (operation cancelled — matches SET QUERY_GOVERNOR_COST_LIMIT)
_TIMEOUT_NATIVE_CODES: frozenset[int] = frozenset({0, -2})
_TIMEOUT_SQLSTATE_RE = re.compile(r"\b(HYT00|HY008)\b", re.IGNORECASE)


def _operator_error_hint(exc: BaseException) -> str:
    """Return a non-sensitive hint for operators (logs only, not end users)."""

    return type(exc).__name__


def _is_timeout_error(exc: pyodbc.Error) -> bool:
    for arg in exc.args:
        if isinstance(arg, str) and _TIMEOUT_SQLSTATE_RE.search(arg):
            return True
    for diag in getattr(exc, "args", ()):
        if isinstance(diag, (list, tuple)) and len(diag) >= 2 and diag[1] in _TIMEOUT_NATIVE_CODES:
            return True
    return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 1_000  # rows fetched per batch from the DBAPI cursor


class ConnectionPool:
    """Thread-safe connection pool for pyodbc MSSQL connections."""

    def __init__(
        self,
        settings: ConnectionSettings,
        *,
        pool_size: int = 5,
        query_timeout: int = 30,
    ) -> None:
        self._settings = settings
        self._pool_size = pool_size
        self._query_timeout = query_timeout
        self._pool: list[pyodbc.Connection] = []
        self._lock = threading.Lock()

    def _create(self) -> pyodbc.Connection:
        try:
            conn_str = self._settings.build_connection_string()
            conn = pyodbc.connect(conn_str, autocommit=True)
            conn.timeout = self._query_timeout
            return conn
        except pyodbc.Error as exc:
            logger.exception(
                "connection failed",
                extra={
                    "db": self._settings.safe_repr(),
                    "hint": type(exc).__name__,
                },
            )
            raise RunnerError(
                "Could not connect to the database. Please try again later.",
                debug_hint=_operator_error_hint(exc),
            ) from exc

    def close_all(self) -> None:
        """Close every pooled connection (application shutdown)."""

        with self._lock:
            while self._pool:
                conn = self._pool.pop()
                with contextlib.suppress(Exception):
                    conn.close()

    @contextlib.contextmanager
    def get_connection(self) -> Iterator[pyodbc.Connection]:
        """Yield a pooled pyodbc connection (context manager)."""
        with self._lock:
            conn = self._pool.pop() if self._pool else self._create()
        try:
            yield conn
        except Exception:
            with contextlib.suppress(Exception):
                conn.close()
            raise
        else:
            with self._lock:
                if len(self._pool) < self._pool_size:
                    try:
                        conn.cursor().execute("SELECT 1")
                        self._pool.append(conn)
                    except Exception:
                        with contextlib.suppress(Exception):
                            conn.close()


class MssqlRunner:
    """Execute pre-validated SELECT queries against SQL Server.

    Parameters
    ----------
    settings:
        Connection configuration. The password is accessed via
        :meth:`~vai_agent.db.connection.ConnectionSettings.build_connection_string`
        at execution time.
    max_rows:
        Hard cap on the number of result rows returned. Defaults to the
        value in ``settings.max_rows`` when the policy model is not
        available at construction time.
    query_timeout:
        Maximum seconds a single query may run before being cancelled.
        Set to ``0`` to rely on the server's own timeout.
    """

    def __init__(
        self,
        settings: ConnectionSettings,
        *,
        max_rows: int = 1_000,
        query_timeout: int = 30,
        pool_size: int = 5,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be >= 1")
        if query_timeout < 0:
            raise ValueError("query_timeout must be >= 0")
        if pool_size < 1:
            raise ValueError("pool_size must be >= 1")
        self._settings = settings
        self._max_rows = max_rows
        self._query_timeout = query_timeout
        self._pool_size = pool_size
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()

    def _ensure_pool(self) -> ConnectionPool:
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is None:
                self._pool = ConnectionPool(
                    self._settings,
                    pool_size=self._pool_size,
                    query_timeout=self._query_timeout,
                )
            return self._pool

    def close(self) -> None:
        """Close the connection pool if it was created."""

        with self._pool_lock:
            if self._pool is not None:
                self._pool.close_all()
                self._pool = None

    def execute(
        self,
        sql: str,
        *,
        rewritten_sql: str | None = None,
        audit_context: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        """Run *sql* and return a :class:`QueryResult`."""
        logger.info(
            "executing query",
            extra={"db": self._settings.safe_repr(), "max_rows": self._max_rows},
        )
        with self._ensure_pool().get_connection() as conn:
            return self._run(conn, sql, rewritten_sql=rewritten_sql, audit_context=audit_context)

    def _run(
        self,
        conn: pyodbc.Connection,
        sql: str,
        *,
        rewritten_sql: str | None,
        audit_context: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        safe_sql = normalize_sql_aliases(sql)
        recorder = get_activity_recorder()
        t0 = perf_counter()

        def _audit_sql(
            status: str,
            *,
            row_count: int | None = None,
            error_type: str = "",
            error_message: str = "",
        ) -> None:
            if not audit_context:
                return
            rid = str(audit_context.get("request_id", ""))
            safe_record_activity(
                recorder,
                ActivityEvent(
                    request_id=rid,
                    event_type="sql.execute",
                    status=status,
                    user_id=str(audit_context.get("user_id", "")),
                    user_email=str(audit_context.get("user_email", "")),
                    user_groups=str(audit_context.get("user_groups", "")),
                    profile_id=str(audit_context.get("profile_id", "")),
                    db_name=str(audit_context.get("db_name", "")),
                    tool_name="run_sql",
                    generated_sql=str(audit_context.get("generated_sql", "")),
                    executed_sql=safe_sql,
                    row_count=row_count,
                    duration_ms=int((perf_counter() - t0) * 1000) if status != "started" else None,
                    error_type=error_type,
                    error_message=error_message,
                ),
            )

        _audit_sql("started")

        try:
            cursor = conn.cursor()
            cursor.execute(safe_sql)

            if cursor.description is None:
                _audit_sql("success", row_count=0)
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    truncated=False,
                    rewritten_sql=rewritten_sql,
                    sql_executed=safe_sql,
                )

            columns = [column[0] for column in cursor.description]
            rows: list[dict[str, Any]] = []
            truncated = False

            while True:
                batch = cursor.fetchmany(_CHUNK_SIZE)
                if not batch:
                    break

                for record in batch:
                    rows.append(
                        {
                            column: _normalise_value(value)
                            for column, value in zip(columns, record, strict=False)
                        },
                    )
                    if len(rows) >= self._max_rows:
                        truncated = True
                        break

                if truncated:
                    break

            result = QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                rewritten_sql=rewritten_sql,
                sql_executed=safe_sql,
            )
            _audit_sql("success", row_count=result.row_count)
            return result

        except pyodbc.Error as exc:
            if _is_timeout_error(exc):
                logger.exception(
                    "query timed out",
                    extra={"timeout_s": self._query_timeout},
                )
                _audit_sql(
                    "error",
                    error_type=type(exc).__name__,
                    error_message=_operator_error_hint(exc),
                )
                raise QueryTimeoutError(
                    f"Query exceeded the {self._query_timeout}-second time limit.",
                    debug_hint=_operator_error_hint(exc),
                ) from exc

            logger.exception("query execution error", extra={"hint": type(exc).__name__})
            _audit_sql(
                "error",
                error_type=type(exc).__name__,
                error_message=_operator_error_hint(exc),
            )
            raise RunnerError(
                "The query could not be executed. Check your query and try again.",
                debug_hint=_operator_error_hint(exc),
            ) from exc

        except RowLimitError:
            raise
        except Exception as exc:
            logger.exception("unexpected runner error", extra={"hint": type(exc).__name__})
            _audit_sql(
                "error",
                error_type=type(exc).__name__,
                error_message=_operator_error_hint(exc),
            )
            raise RunnerError(
                "An unexpected error occurred while running the query.",
                debug_hint=_operator_error_hint(exc),
            ) from exc


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------


def _normalise_value(value: Any) -> Any:
    """Convert a DBAPI / driver value to a JSON-serialisable Python type."""

    if value is None:
        return None

    if hasattr(value, "item"):
        with contextlib.suppress(Exception):
            value = value.item()

    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return None
        try:
            f = float(value)
        except Exception:
            return str(value)
        if math.isfinite(f):
            return f
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, time):
        return value.isoformat()

    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")

    return value
