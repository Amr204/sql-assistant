"""ExplainSchemaTool — read-only schema explainer.

Returns structured information from the loaded :class:`Profile` without
ever touching the database. Two modes:

* No table specified → return a summary list of all tables.
* ``table`` specified → return detailed information for that one table,
  including columns, PK, FKs, indexes, and (if present) the per-table
  profile metadata (business name, grain, …).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from vai_agent.tools.base import ToolBase, ToolResult

if TYPE_CHECKING:
    from vai_agent.knowledge.profile_models import Profile, Table
    from vai_agent.users import User


class ExplainSchemaArgs(BaseModel):
    """Arguments for :class:`ExplainSchemaTool`."""

    table: str | None = Field(
        default=None,
        description=(
            "Optional table name. When omitted, returns a list of all "
            "tables in the schema."
        ),
    )


class ExplainSchemaTool(ToolBase):
    """Explain the loaded database schema; never executes SQL."""

    name = "explain_schema"
    description = (
        "Return information about the database schema. With no argument, "
        "lists every table in the schema with a one-line summary. With a "
        "table name, returns its columns, primary key, foreign keys, and "
        "any per-table profile metadata."
    )
    args_model = ExplainSchemaArgs
    access_groups: tuple[str, ...] = ()

    def __init__(self, profile: Profile) -> None:
        self._profile = profile

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        """Execute pre-validated SQL and return a safe QueryResult."""
        if not isinstance(args, ExplainSchemaArgs):  # pragma: no cover
            return self._fail("Invalid arguments.")

        if args.table is None:
            return self._ok({"tables": [self._summarise(t) for t in self._profile.database_schema.tables]})

        table = self._profile.database_schema.table(args.table)
        if table is None:
            return self._fail(f"Table {args.table!r} not found in profile.")
        return self._ok(self._detail(table))

    # ------------------------------------------------------------------
    # Internal formatters
    # ------------------------------------------------------------------

    def _summarise(self, table: Table) -> dict[str, Any]:
        return {
            "name": table.name,
            "schema": table.schema_name,
            "description": table.description,
            "column_count": len(table.columns),
            "primary_key": list(table.primary_key),
            "foreign_key_count": len(table.foreign_keys),
        }

    def _detail(self, table: Table) -> dict[str, Any]:
        # Merge in any per-table profile metadata if present.
        per_table = self._profile.tables.get(table.name)
        return {
            "name": table.name,
            "schema": table.schema_name,
            "description": table.description,
            "primary_key": list(table.primary_key),
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "default": c.default,
                    "description": c.description,
                }
                for c in table.columns
            ],
            "foreign_keys": [
                {
                    "name": fk.name,
                    "columns": list(fk.columns),
                    "references_schema": fk.references_schema,
                    "references_table": fk.references_table,
                    "references_columns": list(fk.references_columns),
                }
                for fk in table.foreign_keys
            ],
            "indexes": [
                {"name": ix.name, "columns": list(ix.columns), "unique": ix.unique}
                for ix in table.indexes
            ],
            "business_name_ar": per_table.business_name_ar if per_table else None,
            "business_name_en": per_table.business_name_en if per_table else None,
            "grain": per_table.grain if per_table else None,
            "common_questions": (
                list(per_table.common_questions) if per_table else []
            ),
        }
