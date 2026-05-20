"""Vanna tool that runs policy-gated SQL and returns structured rows (no Vanna CSV path)."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from vanna.capabilities.sql_runner.models import RunSqlToolArgs
from vanna.components import (
    DataFrameComponent,
    NotificationComponent,
    SimpleTextComponent,
    UiComponent,
)
from vanna.core.tool import Tool, ToolContext, ToolResult

from vai_agent.vanna_integration.errors import QueryRejectedError
from vai_agent.vanna_integration.policy_sql_runner import PolicySqlRunner

logger = logging.getLogger(__name__)

_PREVIEW_ROWS = 100


def _dataframe_ui(
    *,
    rows: list[dict[str, Any]],
    columns: list[str],
    sql_executed: str,
    execution_ms: int,
    truncated: bool,
) -> UiComponent:
    """Rich payload the API layer can parse (``column_types`` carries VAI metadata)."""

    meta: dict[str, str] = {
        "_vai_sql": sql_executed,
        "_vai_ms": str(execution_ms),
        "_vai_truncated": "1" if truncated else "0",
    }
    if rows:
        comp = DataFrameComponent.from_records(
            rows,
            title="Query Results",
            description="Structured SQL result (no CSV export).",
            exportable=False,
        )
        merged = {**dict(comp.column_types or {}), **meta}
        comp = comp.model_copy(update={"column_types": merged})
    else:
        comp = DataFrameComponent(
            rows=[],
            columns=columns,
            title="Query Results",
            description="Structured SQL result (no rows).",
            exportable=False,
            column_types=meta,
        )
    return UiComponent(
        rich_component=comp,
        simple_component=SimpleTextComponent(
            text="Structured query result is available to the client; do not print CSV or filenames.",
        ),
    )


class VaiRunSqlTool(Tool[RunSqlToolArgs]):
    """Same stack as :class:`PolicySqlRunner` without pandas→CSV ``RunSqlTool`` behaviour."""

    def __init__(
        self,
        policy_runner: PolicySqlRunner,
        *,
        tool_name: str = "run_sql",
        tool_description: str | None = None,
    ) -> None:
        self._policy = policy_runner
        self._tool_name = tool_name
        self._tool_description = tool_description or (
            "Execute safe read-only T-SQL SELECT queries. "
            "Returns structured rows (columns + row dicts) for the UI — never CSV filenames. "
            "Enforces SQL policy, PII rules, row limits, and timeouts."
        )

    @property
    def name(self) -> str:
        """Name."""
        return self._tool_name

    @property
    def description(self) -> str:
        """Description."""
        return self._tool_description

    def get_args_schema(self) -> type[RunSqlToolArgs]:
        """Return args schema."""
        return RunSqlToolArgs

    async def execute(self, context: ToolContext, args: RunSqlToolArgs) -> ToolResult:
        """Execute pre-validated SQL and return a safe QueryResult."""
        t0 = perf_counter()
        try:
            outcome = await self._policy.run_sql_structured(args, context)
        except QueryRejectedError as exc:
            msg = str(exc)
            return ToolResult(
                success=False,
                result_for_llm=msg,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        level="error",
                        message=msg,
                    ),
                    simple_component=SimpleTextComponent(text=msg),
                ),
                error=msg,
                metadata={"error_type": exc.error_code},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("SQL execution failed")
            msg = f"Query execution failed: {type(exc).__name__}"
            return ToolResult(
                success=False,
                result_for_llm=msg,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        level="error",
                        message=msg,
                    ),
                    simple_component=SimpleTextComponent(text=msg),
                ),
                error=type(exc).__name__,
                metadata={"error_type": type(exc).__name__},
            )

        execution_ms = int((perf_counter() - t0) * 1000)
        preview = outcome.rows[: min(10, len(outcome.rows))]
        llm_body: dict[str, Any] = {
            "row_count": outcome.row_count,
            "columns": outcome.columns,
            "sample_rows": preview,
            "truncated": outcome.truncated,
        }
        result_for_llm = (
            "Structured SQL result only — do not mention CSV files, query_results_, "
            "or visualize_data. Summarize insights briefly; tabular detail is in structured data.\n"
            + json.dumps(llm_body, ensure_ascii=False, default=str)
        )

        meta_out: dict[str, Any] = {
            "sql": outcome.sql_executed,
            "columns": outcome.columns,
            "rows": outcome.rows[:_PREVIEW_ROWS],
            "total_row_count": outcome.row_count,
            "execution_ms": execution_ms,
            "truncated": outcome.truncated,
        }

        return ToolResult(
            success=True,
            result_for_llm=result_for_llm,
            ui_component=_dataframe_ui(
                rows=outcome.rows,
                columns=outcome.columns,
                sql_executed=outcome.sql_executed,
                execution_ms=execution_ms,
                truncated=outcome.truncated,
            ),
            metadata=meta_out,
        )
