"""Turn an :class:`ExtractionResult` into a writable :class:`Profile`.

Phase-3 scope is narrow: emit ``profile.yaml``, ``schema.generated.yaml``,
``relationships.yaml`` and ``tables/*.yaml``. The other facets
(``business_rules`` / ``glossary`` / ``metrics`` / ``examples`` /
``security_policy`` / ``sql_style``) are intentionally **not** generated —
Phase-2's loader treats them as optional and falls back to safe defaults.

Why ``profile.yaml`` is included even though the user didn't list it
in the Phase-3 brief: it's mandatory for the loader and therefore
required for the generator's output to be loadable / validatable.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from vai_agent.db.schema_extractor import ExtractionResult
from vai_agent.knowledge.profile_models import (
    Confidence,
    Profile,
    ProfileMeta,
    RelationshipsDocument,
    Table,
    TableProfile,
)

logger = logging.getLogger(__name__)

# Type tokens that signal "this column holds a date/time".
_DATE_TYPE_HINTS = ("DATE", "TIME", "TIMESTAMP")


# ---------------------------------------------------------------------------
# Profile assembly
# ---------------------------------------------------------------------------


def generate_profile(
    *,
    extracted: ExtractionResult,
    profile_id: str,
    database_name: str,
    source_path: str | Path | None = None,
    now: datetime | None = None,
    default_schema: str = "dbo",
    timezone: str = "UTC",
) -> Profile:
    """Build a :class:`Profile` from the schema-extraction result.

    Per-table profiles are produced with low-confidence auto-generated
    defaults; humans are expected to edit the resulting YAML to add
    business names, descriptions, and common questions.
    """

    relationships = list(extracted.relationships)
    tables = {
        t.name: _build_table_profile(t, extracted)
        for t in extracted.database_schema.tables
    }

    return Profile(
        meta=ProfileMeta(
            profile_id=profile_id,
            database_name=database_name,
            default_schema=default_schema,
            timezone=timezone,
            created_at=now or datetime.now(UTC),
            generated_from=str(source_path) if source_path else None,
        ),
        database_schema=extracted.database_schema,
        relationships=RelationshipsDocument(relationships=relationships),
        tables=tables,
    )


def _build_table_profile(table: Table, extracted: ExtractionResult) -> TableProfile:
    incoming = [
        r for r in extracted.relationships
        if r.to_table == table.name
    ]
    outgoing = [
        r for r in extracted.relationships
        if r.from_table == table.name
    ]

    relationship_strings = [
        f"{r.from_table} ({_cardinality_left(r)}) -> "
        f"{r.to_table} ({_cardinality_right(r)}) via {','.join(r.from_columns)}"
        for r in outgoing
    ] + [
        f"{r.from_table} ({_cardinality_left(r)}) -> "
        f"{r.to_table} ({_cardinality_right(r)}) via {','.join(r.from_columns)}"
        for r in incoming
        if r.from_table != table.name  # avoid duplicating self-FKs
    ]

    return TableProfile(
        name=table.name,
        schema_name=table.schema_name,
        primary_key=list(table.primary_key),
        important_columns=_pick_important_columns(table),
        date_columns=[
            c.name for c in table.columns
            if any(h in c.type.upper() for h in _DATE_TYPE_HINTS)
        ],
        relationships=relationship_strings,
        confidence=Confidence.low,
    )


def _pick_important_columns(table: Table, limit: int = 5) -> list[str]:
    """Heuristic: PK columns first, then up to ``limit`` NOT NULL columns."""

    seen: set[str] = set()
    ordered: list[str] = []
    for col in table.primary_key:
        if col not in seen:
            seen.add(col)
            ordered.append(col)
    for col in table.columns:
        if col.name in seen:
            continue
        if not col.nullable:
            seen.add(col.name)
            ordered.append(col.name)
        if len(ordered) >= limit:
            break
    return ordered[:limit]


def _cardinality_left(r: Any) -> str:
    # many_to_one / one_to_many / one_to_one / many_to_many
    return r.cardinality.value.split("_to_")[0]


def _cardinality_right(r: Any) -> str:
    return r.cardinality.value.split("_to_")[1]


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


def write_profile_to_disk(
    profile: Profile,
    output_dir: Path | str,
    *,
    force: bool = False,
) -> list[Path]:
    """Serialise ``profile`` to ``output_dir/*.yaml`` and return the paths.

    Parameters
    ----------
    profile:
        The :class:`Profile` to write.
    output_dir:
        Target directory (e.g. ``profiles/default``). Created if needed.
    force:
        Overwrite the directory even if ``profile.yaml`` already exists.
        Without ``force=True`` an existing profile is refused.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if (output_dir / "profile.yaml").exists() and not force:
        raise FileExistsError(
            f"profile.yaml already exists at {output_dir}; pass force=True to overwrite"
        )

    written: list[Path] = []
    written.append(_write_yaml(
        output_dir / "profile.yaml",
        profile.meta.model_dump(mode="json", by_alias=True, exclude_none=True),
    ))
    written.append(_write_yaml(
        output_dir / "schema.generated.yaml",
        profile.database_schema.model_dump(mode="json", by_alias=True, exclude_none=True),
    ))
    written.append(_write_yaml(
        output_dir / "relationships.yaml",
        profile.relationships.model_dump(mode="json", by_alias=True, exclude_none=True),
    ))

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    for name, table_profile in profile.tables.items():
        filename = f"{_safe_filename(name)}.yaml"
        written.append(_write_yaml(
            tables_dir / filename,
            table_profile.model_dump(mode="json", by_alias=True, exclude_none=True),
        ))

    logger.info(
        "profile written",
        extra={"profile_id": profile.meta.profile_id, "files": len(written)},
    )
    return written


def _safe_filename(name: str) -> str:
    """Turn a table name into an OS-friendly filename stem.

    Spaces become underscores; any character outside ``[A-Za-z0-9_-]``
    is stripped. The original (space-bearing) ``name`` field inside the
    file is preserved — the loader keys per-table profiles by the
    ``name`` attribute, not by filename.
    """

    cleaned = re.sub(r"\s+", "_", name.strip())
    cleaned = re.sub(r"[^\w\-]", "", cleaned)
    return cleaned or "table"


def _write_yaml(path: Path, data: Any) -> Path:
    text = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=120,
    )
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Schema file I/O
# ---------------------------------------------------------------------------


def read_schema_file(path: Path | str) -> str:
    """Read a SQL DDL file with BOM-based encoding detection.

    SSMS's ``Script Database As`` defaults to UTF-16 LE with a BOM, so
    the typical input file is *not* plain UTF-8. We detect the BOM and
    pick the right codec; fall back to UTF-8 otherwise.
    """

    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le")[1:]  # strip BOM
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be")[1:]
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")
