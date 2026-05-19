"""ProfileSearchTool — keyword search across the profile knowledge base.

Searches a substring (case-insensitive) across:

* Glossary terms (``canonical`` / ``ar`` / ``en`` / ``synonyms``).
* Table and column names + descriptions.
* Business rules (descriptions).
* Metrics (names, descriptions).
* Per-table profile fields (business names, grain).

Substring matching is deliberately simple — no LLM, no vector store.
Future phases will add an embedding-based retriever; this tool gives
the agent an offline, deterministic fallback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from vai_agent.tools.base import ToolBase, ToolResult

if TYPE_CHECKING:
    from vai_agent.knowledge.profile_models import Profile
    from vai_agent.users import User


class ProfileSearchArgs(BaseModel):
    """Arguments for :class:`ProfileSearchTool`."""

    query: str = Field(min_length=1, description="Substring to search for (case-insensitive).")
    limit: int = Field(default=20, ge=1, le=100)


class ProfileSearchTool(ToolBase):
    """Substring search across the loaded profile's knowledge facets."""

    name = "profile_search"
    description = (
        "Search the database profile (glossary, table/column names and "
        "descriptions, business rules, metrics) for a substring. "
        "Returns matches grouped by source. Case-insensitive."
    )
    args_model = ProfileSearchArgs
    access_groups: tuple[str, ...] = ()

    def __init__(self, profile: Profile) -> None:
        self._profile = profile

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        if not isinstance(args, ProfileSearchArgs):  # pragma: no cover
            return self._fail("Invalid arguments.")

        needle = args.query.lower()
        hits: list[dict[str, Any]] = []

        hits.extend(self._search_glossary(needle))
        hits.extend(self._search_tables(needle))
        hits.extend(self._search_columns(needle))
        hits.extend(self._search_business_rules(needle))
        hits.extend(self._search_metrics(needle))
        hits.extend(self._search_per_table(needle))

        total_hits = len(hits)
        truncated = total_hits > args.limit
        hits = hits[: args.limit]
        return self._ok(
            {"query": args.query, "hits": hits, "total_hits": total_hits},
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # Internal searchers
    # ------------------------------------------------------------------

    def _search_glossary(self, needle: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for term in self._profile.glossary.terms:
            haystack = " ".join([
                term.canonical,
                *term.ar,
                *term.en,
                *term.synonyms,
            ]).lower()
            if needle in haystack:
                out.append({
                    "source": "glossary",
                    "canonical": term.canonical,
                    "ar": list(term.ar),
                    "en": list(term.en),
                    "synonyms": list(term.synonyms),
                    "maps_to_tables": list(term.maps_to.tables),
                })
        return out

    def _search_tables(self, needle: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for t in self._profile.database_schema.tables:
            haystack = " ".join([t.name, t.description or ""]).lower()
            if needle in haystack:
                out.append({
                    "source": "table",
                    "name": t.name,
                    "schema": t.schema_name,
                    "description": t.description,
                })
        return out

    def _search_columns(self, needle: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for t in self._profile.database_schema.tables:
            for c in t.columns:
                haystack = f"{c.name} {c.description or ''}".lower()
                if needle in haystack:
                    out.append({
                        "source": "column",
                        "table": t.name,
                        "name": c.name,
                        "type": c.type,
                        "description": c.description,
                    })
        return out

    def _search_business_rules(self, needle: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for rule in self._profile.business_rules.rules:
            if needle in rule.description.lower():
                out.append({
                    "source": "business_rule",
                    "id": rule.id,
                    "description": rule.description,
                    "tables": list(rule.tables),
                })
        return out

    def _search_metrics(self, needle: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in self._profile.metrics.metrics:
            haystack = " ".join([
                m.name_en or "",
                m.name_ar or "",
                m.description or "",
            ]).lower()
            if needle in haystack:
                out.append({
                    "source": "metric",
                    "id": m.id,
                    "name_en": m.name_en,
                    "name_ar": m.name_ar,
                    "description": m.description,
                })
        return out

    def _search_per_table(self, needle: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name, tp in self._profile.tables.items():
            haystack = " ".join([
                tp.business_name_ar or "",
                tp.business_name_en or "",
                tp.description or "",
                tp.grain or "",
            ]).lower()
            if needle in haystack:
                out.append({
                    "source": "table_profile",
                    "name": name,
                    "business_name_ar": tp.business_name_ar,
                    "business_name_en": tp.business_name_en,
                    "grain": tp.grain,
                })
        return out
