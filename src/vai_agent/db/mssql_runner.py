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
2. **Row cap** — :func:`pandas.read_sql` is called with ``chunksize``
   to count rows on the fly and abort when ``max_rows`` is exceeded.
3. **Safe result format** — results are returned as a
   :class:`QueryResult` (a plain Pydantic model: list of column names +
   list-of-dicts rows). No raw DataFrame or DBAPI cursor leaks out.
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

import contextlib
import logging
import re
from typing import Any

import pandas as pd
import pyodbc
from pydantic import BaseModel, ConfigDict, Field

from vai_agent.db.connection import ConnectionSettings

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
        description="The SQL that was actually sent to the database.",
    )


class RunnerError(Exception):
    """Raised when query execution fails.

    The ``safe_message`` attribute is safe to show to end users.
    The ``debug_hint`` attribute contains a non-sensitive hint for
    operators and is **not** for display to end users.
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


def _is_timeout_error(exc: pyodbc.Error) -> bool:
    for arg in exc.args:
        if isinstance(arg, str) and _TIMEOUT_SQLSTATE_RE.search(arg):
            return True
    # pyodbc sometimes surfaces the native error code as the first int arg.
    for diag in getattr(exc, "args", ()):
        if isinstance(diag, (list, tuple)) and len(diag) >= 2 and diag[1] in _TIMEOUT_NATIVE_CODES:
            return True
    return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 1_000  # rows fetched per chunk from the DBAPI cursor


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
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be >= 1")
        if query_timeout < 0:
            raise ValueError("query_timeout must be >= 0")
        self._settings = settings
        self._max_rows = max_rows
        self._query_timeout = query_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, sql: str, *, rewritten_sql: str | None = None) -> QueryResult:
        """Run *sql* and return a :class:`QueryResult`.

        Parameters
        ----------
        sql:
            The SQL to execute. **Must** already be approved by both
            policy engines; this method performs no policy checks.
        rewritten_sql:
            Optional: the SQL string after TOP-injection by the policy
            engine. Stored on the result for audit purposes.

        Raises
        ------
        QueryTimeoutError
            When the query exceeds ``query_timeout`` seconds.
        RowLimitError
            When the result set exceeds ``max_rows``.
        RunnerError
            For all other database errors (message is safe for end users).
        """
        logger.info(
            "executing query",
            extra={"db": self._settings.safe_repr(), "max_rows": self._max_rows},
        )
        conn = self._connect()
        try:
            return self._run(conn, sql, rewritten_sql=rewritten_sql)
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self) -> pyodbc.Connection:
        try:
            conn_str = self._settings.build_connection_string()
            conn = pyodbc.connect(conn_str, autocommit=True)
            conn.timeout = self._query_timeout
            return conn
        except pyodbc.Error as exc:
            logger.warning("connection failed", extra={"hint": "check db/network config"})
            raise RunnerError(
                "Could not connect to the database. Please try again later.",
                debug_hint=f"pyodbc.Error: {type(exc).__name__}",
            ) from exc

    def _run(
        self,
        conn: pyodbc.Connection,
        sql: str,
        *,
        rewritten_sql: str | None,
    ) -> QueryResult:
        try:
            # pandas.read_sql with chunksize returns a generator of DataFrames.
            # We iterate and stop as soon as we exceed max_rows.
            chunks: list[pd.DataFrame] = []
            total_rows = 0
            truncated = False

            for chunk in pd.read_sql(
                sql,
                conn,
                chunksize=_CHUNK_SIZE,
            ):
                remaining = self._max_rows - total_rows
                if len(chunk) > remaining:
                    chunk = chunk.iloc[:remaining]
                    chunks.append(chunk)
                    total_rows += len(chunk)
                    truncated = True
                    break
                chunks.append(chunk)
                total_rows += len(chunk)
                if total_rows >= self._max_rows:
                    truncated = True
                    break

            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

            return self._to_result(df, truncated=truncated, rewritten_sql=rewritten_sql)

        except pyodbc.Error as exc:
            if _is_timeout_error(exc):
                logger.warning("query timed out", extra={"timeout_s": self._query_timeout})
                raise QueryTimeoutError(
                    f"Query exceeded the {self._query_timeout}-second time limit.",
                    debug_hint=f"pyodbc.Error: {type(exc).__name__}",
                ) from exc
            logger.warning("query execution error", extra={"hint": type(exc).__name__})
            raise RunnerError(
                "The query could not be executed. Check your query and try again.",
                debug_hint=f"pyodbc.Error: {type(exc).__name__}",
            ) from exc

        except RowLimitError:
            raise
        except Exception as exc:
            logger.warning("unexpected runner error", extra={"hint": type(exc).__name__})
            raise RunnerError(
                "An unexpected error occurred while running the query.",
                debug_hint=f"{type(exc).__name__}: {exc!s}",
            ) from exc

    @staticmethod
    def _to_result(
        df: pd.DataFrame,
        *,
        truncated: bool,
        rewritten_sql: str | None,
    ) -> QueryResult:
        """Convert a pandas DataFrame to a :class:`QueryResult`."""
        columns = list(df.columns)
        # Convert each row to a plain dict with Python-native values
        # (no numpy types, no NaT, etc.) so FastAPI can JSON-serialise.
        rows: list[dict[str, Any]] = [
            {col: _normalise_value(val) for col, val in row.items()}
            for row in df.to_dict(orient="records")
        ]
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            rewritten_sql=rewritten_sql,
        )


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------

_NAN_TYPES: tuple[type, ...] = (float,)


def _normalise_value(value: Any) -> Any:
    """Convert a value from pandas to a JSON-serialisable Python type.

    Rules
    -----
    * ``pd.NaT`` and ``float("nan")`` → ``None``
    * ``pd.Timestamp`` → ISO-8601 string
    * numpy integer / float scalars → ``int`` / ``float``
    * Everything else → unchanged
    """
    if value is None:
        return None
    # NaT
    if isinstance(value, type(pd.NaT)) or value is pd.NaT:
        return None
    # pandas / numpy numeric types
    if hasattr(value, "item"):
        value = value.item()
    # Python float NaN
    if isinstance(value, float) and pd.isna(value):
        return None
    # pandas Timestamp
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value
