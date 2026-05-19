"""Parse SQL Server SSMS-style DDL into Phase-2 schema models.

The input we target is the output of *SQL Server Management Studio*'s
``Script Database As`` feature. That format is highly regular and
amenable to a focused, dependency-free, regex-based parser:

* Bracketed identifiers (``[dbo].[Order Details]``).
* ``GO`` batch separators.
* One CREATE statement per batch.
* Constraints (PK, FK, DEFAULT) declared in-line or via ALTER TABLE.
* ``CREATE [UNIQUE] [NONCLUSTERED|CLUSTERED] INDEX``.

What this module does NOT do
----------------------------
* It does not parse general SQL — only the SSMS DDL subset above.
* It does not extract CHECK constraints (Phase 2's ``Table`` model
  has no place for them; revisit if/when the SQL execution layer needs
  them).
* It does not extract view / stored-procedure *bodies* semantically;
  it stores them as raw definition text in ``View.definition`` /
  ``StoredProcedure.definition``.

If/when full SQL semantics are needed, this module can be replaced
with a ``sqlglot``-based implementation behind the same
:func:`parse_schema_sql` signature.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from vai_agent.knowledge.profile_models import (
    Cardinality,
    Column,
    Confidence,
    DatabaseSchema,
    ForeignKeyDef,
    IndexDef,
    JoinType,
    Relationship,
    RelationshipKind,
    StoredProcedure,
    Table,
    View,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Bundled output of :func:`parse_schema_sql`."""

    database_schema: DatabaseSchema = Field(default_factory=DatabaseSchema)
    relationships: list[Relationship] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal dataclasses for intermediate FK / DEFAULT parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ParsedFK:
    source_table: str
    fk: ForeignKeyDef


@dataclass(frozen=True)
class _ParsedDefault:
    table: str
    column: str
    expression: str


@dataclass(frozen=True)
class _ParsedIndex:
    table: str
    index: IndexDef


# ---------------------------------------------------------------------------
# Regex toolkit
# ---------------------------------------------------------------------------

_QUALIFIED_NAME = r"\[(?P<schema>\w+)\]\.\[(?P<name>[^\]]+)\]"

_CREATE_TABLE_RE = re.compile(
    rf"\bCREATE\s+TABLE\s+{_QUALIFIED_NAME}\s*\(",
    re.IGNORECASE,
)

_PK_CONSTRAINT_RE = re.compile(
    r"^\s*CONSTRAINT\s+\[[^\]]+\]\s+PRIMARY\s+KEY\b",
    re.IGNORECASE,
)

_COLUMN_HEAD_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s+(?P<rest>.+)\s*$", re.DOTALL)
_TYPE_RE = re.compile(
    r"^\[?(?P<type>\w+)\]?\s*(?P<size>\(\s*[\d,\s]+\s*\))?",
    re.IGNORECASE,
)
_IDENTITY_RE = re.compile(r"\bIDENTITY\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)
_NOT_NULL_RE = re.compile(r"\bNOT\s+NULL\b", re.IGNORECASE)
_NULL_RE = re.compile(r"\bNULL\b", re.IGNORECASE)

_FK_RE = re.compile(
    rf"\bALTER\s+TABLE\s+{_QUALIFIED_NAME.replace('schema', 'src_schema').replace('name', 'src_table')}"
    r"\s+(?:WITH\s+(?:CHECK|NOCHECK)\s+)?ADD\s+CONSTRAINT\s+\[(?P<fk_name>[^\]]+)\]"
    r"\s+FOREIGN\s+KEY\s*\((?P<src_cols>[^)]+)\)"
    r"\s+REFERENCES\s+\[(?P<ref_schema>\w+)\]\.\[(?P<ref_table>[^\]]+)\]"
    r"\s*\((?P<ref_cols>[^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)

_DEFAULT_RE = re.compile(
    rf"\bALTER\s+TABLE\s+{_QUALIFIED_NAME}"
    r"\s+ADD\s+(?:CONSTRAINT\s+\[[^\]]+\]\s+)?DEFAULT\s+(?P<expr>.+?)\s+FOR\s+\[(?P<col>[^\]]+)\]",
    re.IGNORECASE | re.DOTALL,
)

_INDEX_RE = re.compile(
    r"\bCREATE\s+(?P<unique>UNIQUE\s+)?(?:NONCLUSTERED|CLUSTERED)?\s*INDEX\s+\[(?P<idx_name>[^\]]+)\]"
    rf"\s+ON\s+{_QUALIFIED_NAME}\s*\(",
    re.IGNORECASE,
)

_VIEW_RE = re.compile(
    rf"\bCREATE\s+VIEW\s+{_QUALIFIED_NAME}\s+AS\s+(?P<body>.+)",
    re.IGNORECASE | re.DOTALL,
)

_PROC_RE = re.compile(
    rf"\bCREATE\s+PROCEDURE\s+{_QUALIFIED_NAME}(?P<rest>.+)",
    re.IGNORECASE | re.DOTALL,
)

_BRACKETED_NAME_RE = re.compile(r"\[([^\]]+)\]")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def split_go_batches(text: str) -> list[str]:
    """Split a SSMS DDL script on its ``GO`` batch separators.

    ``GO`` must appear alone on its own line (whitespace permitted).
    Lines that are part of a SQL string literal are not handled
    specially — SSMS never emits ``GO`` inside a literal so this is safe
    for our target format.
    """

    batches: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        if raw_line.strip().upper() == "GO":
            joined = "\n".join(current).strip()
            if joined:
                batches.append(joined)
            current = []
        else:
            current.append(raw_line)
    tail = "\n".join(current).strip()
    if tail:
        batches.append(tail)
    return batches


def _balanced_paren_end(text: str, start: int) -> int:
    """Given ``text[start] == '('``, return the index of the matching ``)``.

    Tracks single- and double-quoted strings so embedded parentheses
    inside a string literal are ignored.
    """

    if start >= len(text) or text[start] != "(":
        raise ValueError(f"expected '(' at position {start}, got {text[start:start+1]!r}")

    depth = 0
    in_string: str | None = None
    i = start
    while i < len(text):
        ch = text[i]
        if in_string is not None:
            if ch == in_string:
                in_string = None
        elif ch in ("'", '"'):
            in_string = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced parentheses")


def _split_top_level_commas(body: str) -> list[str]:
    """Split ``body`` on commas, ignoring those inside nested parens / strings."""

    items: list[str] = []
    start = 0
    depth = 0
    in_string: str | None = None
    for i, ch in enumerate(body):
        if in_string is not None:
            if ch == in_string:
                in_string = None
        elif ch in ("'", '"'):
            in_string = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append(body[start:i])
            start = i + 1
    tail = body[start:]
    if tail.strip():
        items.append(tail)
    return items


def _split_bracketed_columns(s: str) -> list[str]:
    """Extract identifiers from a comma list like ``[A], [B]``."""

    return [m.group(1) for m in _BRACKETED_NAME_RE.finditer(s)]


# ---------------------------------------------------------------------------
# Statement-level parsers
# ---------------------------------------------------------------------------


def _parse_column(item: str) -> Column | None:
    head = _COLUMN_HEAD_RE.match(item)
    if not head:
        return None
    name = head.group("name")
    rest = head.group("rest").strip()

    type_m = _TYPE_RE.match(rest)
    if not type_m:
        return None
    type_token = type_m.group("type")
    size = (type_m.group("size") or "").replace(" ", "")
    type_str = f"{type_token}{size}".strip()
    tail = rest[type_m.end():]

    identity_m = _IDENTITY_RE.search(tail)
    if identity_m:
        type_str = f"{type_str} IDENTITY({identity_m.group(1)},{identity_m.group(2)})"
        tail = tail.replace(identity_m.group(0), "", 1)

    if _NOT_NULL_RE.search(tail):
        nullable = False
    elif _NULL_RE.search(tail):
        nullable = True
    else:
        nullable = True

    return Column(name=name, type=type_str, nullable=nullable)


def _parse_pk_columns(item: str) -> list[str]:
    """Parse the column list of a ``CONSTRAINT ... PRIMARY KEY (...)`` item."""

    paren_start = item.find("(")
    if paren_start < 0:
        return []
    paren_end = _balanced_paren_end(item, paren_start)
    inner = item[paren_start + 1 : paren_end]
    cols: list[str] = []
    for part in inner.split(","):
        m = _BRACKETED_NAME_RE.search(part)
        if m:
            cols.append(m.group(1))
    return cols


def _parse_create_table(batch: str) -> Table | None:
    m = _CREATE_TABLE_RE.search(batch)
    if not m:
        return None

    schema_name = m.group("schema")
    table_name = m.group("name")

    paren_start = m.end() - 1
    try:
        paren_end = _balanced_paren_end(batch, paren_start)
    except ValueError:
        logger.warning("unbalanced parens in CREATE TABLE %s.%s", schema_name, table_name)
        return None

    body = batch[paren_start + 1 : paren_end]
    columns: list[Column] = []
    primary_key: list[str] = []

    for raw_item in _split_top_level_commas(body):
        item = raw_item.strip()
        if not item:
            continue
        if _PK_CONSTRAINT_RE.match(item):
            primary_key = _parse_pk_columns(item)
        elif item.upper().startswith("CONSTRAINT"):
            continue
        else:
            col = _parse_column(item)
            if col is not None:
                columns.append(col)

    return Table(
        name=table_name,
        schema_name=schema_name,
        columns=columns,
        primary_key=primary_key,
    )


def _parse_foreign_key(batch: str) -> _ParsedFK | None:
    m = _FK_RE.search(batch)
    if not m:
        return None
    return _ParsedFK(
        source_table=m.group("src_table"),
        fk=ForeignKeyDef(
            name=m.group("fk_name"),
            columns=_split_bracketed_columns(m.group("src_cols")),
            references_table=m.group("ref_table"),
            references_schema=m.group("ref_schema"),
            references_columns=_split_bracketed_columns(m.group("ref_cols")),
        ),
    )


def _parse_default(batch: str) -> _ParsedDefault | None:
    m = _DEFAULT_RE.search(batch)
    if not m:
        return None
    return _ParsedDefault(
        table=m.group("name"),
        column=m.group("col"),
        expression=m.group("expr").strip(),
    )


def _parse_index(batch: str) -> _ParsedIndex | None:
    m = _INDEX_RE.search(batch)
    if not m:
        return None
    paren_start = m.end() - 1
    try:
        paren_end = _balanced_paren_end(batch, paren_start)
    except ValueError:
        return None
    cols = _split_bracketed_columns(batch[paren_start + 1 : paren_end])
    return _ParsedIndex(
        table=m.group("name"),
        index=IndexDef(
            name=m.group("idx_name"),
            columns=cols,
            unique=bool(m.group("unique")),
        ),
    )


def _parse_view(batch: str) -> View | None:
    m = _VIEW_RE.search(batch)
    if not m:
        return None
    return View(
        name=m.group("name"),
        schema_name=m.group("schema"),
        definition=m.group("body").strip(),
    )


def _parse_procedure(batch: str) -> StoredProcedure | None:
    m = _PROC_RE.search(batch)
    if not m:
        return None
    return StoredProcedure(
        name=m.group("name"),
        schema_name=m.group("schema"),
        definition=m.group("rest").strip(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_schema_sql(text: str) -> ExtractionResult:
    """Parse a SSMS-style DDL script into Phase-2 schema models.

    The result holds a ready-to-serialise :class:`DatabaseSchema` (with
    columns, primary keys, foreign keys, indexes, views, and stored
    procedures attached to the right tables) and a list of derived
    :class:`Relationship` objects ready for ``relationships.yaml``.
    """

    tables_by_key: dict[str, Table] = {}
    views: list[View] = []
    procedures: list[StoredProcedure] = []
    fks: list[_ParsedFK] = []
    defaults: list[_ParsedDefault] = []
    indexes: list[_ParsedIndex] = []

    # We try parsers in order of specificity. The wrapper statements
    # (CREATE PROCEDURE, CREATE VIEW) are attempted first so that
    # keywords appearing inside their bodies cannot trick the simpler
    # parsers. SSMS emits each statement in its own ``GO`` batch (with a
    # leading ``/****** Object ... ******/`` comment that the regexes
    # tolerate because they use ``re.search`` with ``\b``).
    for batch in split_go_batches(text):
        if (proc := _parse_procedure(batch)) is not None:
            procedures.append(proc)
            continue
        if (view := _parse_view(batch)) is not None:
            views.append(view)
            continue
        if (table := _parse_create_table(batch)) is not None:
            tables_by_key[f"{table.schema_name}.{table.name}"] = table
            continue
        if (parsed_idx := _parse_index(batch)) is not None:
            indexes.append(parsed_idx)
            continue
        if (parsed_fk := _parse_foreign_key(batch)) is not None:
            fks.append(parsed_fk)
            continue
        if (parsed_def := _parse_default(batch)) is not None:
            defaults.append(parsed_def)
            continue

    def _resolve_table(name: str) -> Table | None:
        if name in tables_by_key:
            return tables_by_key[name]
        matches = [
            t for key, t in tables_by_key.items()
            if t.name == name or key.endswith(f".{name}")
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    # Attach FKs / indexes / defaults to their owning tables.
    for parsed_fk in fks:
        table = _resolve_table(parsed_fk.source_table)
        if table is None:
            logger.warning(
                "foreign key %s references unknown source table %s",
                parsed_fk.fk.name, parsed_fk.source_table,
            )
            continue
        table.foreign_keys.append(parsed_fk.fk)

    for parsed_idx in indexes:
        table = _resolve_table(parsed_idx.table)
        if table is None:
            logger.warning("index %s on unknown table %s", parsed_idx.index.name, parsed_idx.table)
            continue
        table.indexes.append(parsed_idx.index)

    for d in defaults:
        table = _resolve_table(d.table)
        if table is None:
            continue
        for col in table.columns:
            if col.name == d.column:
                col.default = d.expression
                break

    relationships = [_fk_to_relationship(pfk) for pfk in fks]

    return ExtractionResult(
        database_schema=DatabaseSchema(
            tables=list(tables_by_key.values()),
            views=views,
            stored_procedures=procedures,
        ),
        relationships=relationships,
    )


# ---------------------------------------------------------------------------
# Relationship derivation
# ---------------------------------------------------------------------------


def _safe_id_part(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_").lower()


def _fk_to_relationship(parsed: _ParsedFK) -> Relationship:
    rel_id = f"rel_{_safe_id_part(parsed.source_table)}_{_safe_id_part(parsed.fk.references_table)}"
    return Relationship(
        id=rel_id,
        from_table=parsed.source_table,
        from_columns=parsed.fk.columns,
        to_table=parsed.fk.references_table,
        to_columns=parsed.fk.references_columns,
        kind=RelationshipKind.foreign_key,
        cardinality=Cardinality.many_to_one,
        join_type=JoinType.inner,
        confidence=Confidence.high,
        reason=f"Explicit foreign key constraint {parsed.fk.name or '(unnamed)'}.",
    )
