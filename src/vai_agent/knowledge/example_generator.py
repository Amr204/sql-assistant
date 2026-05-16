"""Deterministic training-example and eval-question generators.

Phase 9 produces templated ``examples.yaml`` and ``eval_questions.yaml``
from a loaded :class:`Profile`. No LLM is used — every SQL string is built
from schema metadata (tables, columns, PKs, FKs, date columns).

``eval_questions.yaml`` is for offline evaluation only and must **not**
be passed to :func:`vai_agent.memory.chunking.chunk_profile` (the memory
seeder reads ``profile.examples`` exclusively).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from vai_agent.knowledge.profile_models import (
    Confidence,
    Difficulty,
    EvalQuestion,
    EvalQuestionsDocument,
    Example,
    ExamplesDocument,
)

if TYPE_CHECKING:
    from vai_agent.knowledge.profile_models import Profile, Relationship, Table

logger = logging.getLogger(__name__)

_DATE_TYPE_HINTS = ("DATE", "TIME", "TIMESTAMP")
_FILTER_COLUMN_HINTS = ("country", "city", "region", "category", "status", "title")
_TOP_LIMITS = (5, 10, 20)


@dataclass(frozen=True)
class _TableCtx:
    name: str
    schema: str
    pk_cols: list[str]
    label_col: str | None
    date_col: str | None
    group_col: str | None
    qualified: str
    slug: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_examples(
    profile: Profile,
    *,
    min_count: int = 150,
) -> ExamplesDocument:
    """Build templated training examples from *profile* schema metadata."""
    contexts = [_build_table_ctx(t, profile.meta.default_schema) for t in profile.database_schema.tables]
    examples: list[Example] = []
    seq = 0

    for ctx in contexts:
        if not ctx.pk_cols:
            continue
        seq = _extend(examples, _lookup_examples(ctx, seq))
        seq = _extend(examples, _count_examples(ctx, seq))
        if ctx.group_col:
            seq = _extend(examples, _group_examples(ctx, seq))
        if ctx.date_col:
            seq = _extend(examples, _latest_examples(ctx, seq))
            seq = _extend(examples, _trend_examples(ctx, seq))
        if ctx.group_col and ctx.label_col:
            seq = _extend(examples, _filter_examples(ctx, seq))

    for rel in profile.relationships.relationships:
        if rel.kind.value != "foreign_key":
            continue
        child = _ctx_by_name(contexts, rel.from_table)
        parent = _ctx_by_name(contexts, rel.to_table)
        if child and parent:
            seq = _extend(examples, _join_examples(child, parent, rel, seq))

    seq = _extend(examples, _rejected_examples(profile, seq))

    # Scale up with extra TOP-N variants until min_count is met.
    while len(examples) < min_count and contexts:
        for ctx in contexts:
            if not ctx.pk_cols or not ctx.label_col:
                continue
            for n in _TOP_LIMITS:
                seq = _extend(examples, _lookup_examples(ctx, seq, top_n=n, suffix=f"_{n}"))
                if len(examples) >= min_count:
                    break
            if len(examples) >= min_count:
                break

    logger.info(
        "generated examples",
        extra={"profile_id": profile.meta.profile_id, "count": len(examples)},
    )
    return ExamplesDocument(examples=examples)


def generate_eval_questions(
    profile: Profile,
    *,
    min_count: int = 30,
) -> EvalQuestionsDocument:
    """Build held-out evaluation questions (subset of intents + reject cases)."""
    questions: list[EvalQuestion] = []
    seq = 0
    schema = profile.database_schema

    for table in schema.tables[: min(len(schema.tables), 15)]:
        seq += 1
        questions.append(EvalQuestion(
            id=f"eval_{seq:03d}",
            question_en=f"How many rows are in {table.name}?",
            question_ar=f"كم عدد السجلات في جدول {table.name}؟",
            expected_tables=[table.name],
            tags=["count", "simple"],
        ))

    for rel in profile.relationships.relationships[:20]:
        seq += 1
        questions.append(EvalQuestion(
            id=f"eval_{seq:03d}",
            question_en=f"List {rel.from_table} rows with their related {rel.to_table} names.",
            question_ar=f"اعرض سجلات {rel.from_table} مع أسماء {rel.to_table} المرتبطة.",
            expected_tables=[rel.from_table, rel.to_table],
            tags=["join", "medium"],
        ))

    reject_templates = [
        (
            "احذف جميع العملاء",
            "Delete all customers",
            ["destructive"],
        ),
        (
            "أعطني كل أعمدة جدول العملاء SELECT *",
            "Show all columns from customers using SELECT *",
            ["select_star"],
        ),
        (
            "استعلم عن sys.tables",
            "Query sys.tables for schema",
            ["blocked_schema"],
        ),
    ]
    for ar, en, tags in reject_templates:
        seq += 1
        questions.append(EvalQuestion(
            id=f"eval_{seq:03d}",
            question_ar=ar,
            question_en=en,
            expected_tables=[],
            tags=[*tags, "rejected"],
            must_reject=True,
        ))

    while len(questions) < min_count and schema.tables:
        table = schema.tables[len(questions) % len(schema.tables)]
        seq += 1
        questions.append(EvalQuestion(
            id=f"eval_{seq:03d}",
            question_en=f"Show the first 5 rows from {table.name}.",
            question_ar=f"أعرض أول 5 سجلات من {table.name}.",
            expected_tables=[table.name],
            tags=["lookup", "simple"],
        ))

    return EvalQuestionsDocument(questions=questions)


def write_examples_yaml(path: Path, document: ExamplesDocument) -> None:
    """Serialize *document* to ``examples.yaml``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = document.model_dump(mode="json", exclude_none=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def write_eval_questions_yaml(path: Path, document: EvalQuestionsDocument) -> None:
    """Serialize *document* to ``eval_questions.yaml``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = document.model_dump(mode="json", exclude_none=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Table context helpers
# ---------------------------------------------------------------------------


def _build_table_ctx(table: Table, default_schema: str) -> _TableCtx:
    schema = table.schema_name or default_schema
    pk_cols = list(table.primary_key)
    label_col = _pick_label_column(table, pk_cols)
    date_col = next(
        (c.name for c in table.columns if any(h in c.type.upper() for h in _DATE_TYPE_HINTS)),
        None,
    )
    group_col = next(
        (
            c.name
            for c in table.columns
            if c.name.lower() in _FILTER_COLUMN_HINTS or c.name.lower().endswith("name")
        ),
        None,
    )
    if group_col == label_col:
        group_col = next(
            (
                c.name
                for c in table.columns
                if c.name.lower() in _FILTER_COLUMN_HINTS and c.name != label_col
            ),
            None,
        )
    return _TableCtx(
        name=table.name,
        schema=schema,
        pk_cols=pk_cols,
        label_col=label_col,
        date_col=date_col,
        group_col=group_col,
        qualified=_qualify(schema, table.name),
        slug=_slug(table.name),
    )


def _pick_label_column(table: Table, pk_cols: list[str]) -> str | None:
    for col in table.columns:
        if col.name not in pk_cols and "CHAR" in col.type.upper():
            return col.name
    for col in table.columns:
        if col.name not in pk_cols:
            return col.name
    return pk_cols[0] if pk_cols else None


def _qualify(schema: str, table: str) -> str:
    if re.search(r"[^A-Za-z0-9_]", table):
        return f"{schema}.[{table}]"
    return f"{schema}.{table}"


def _slug(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "table"


def _ctx_by_name(contexts: list[_TableCtx], name: str) -> _TableCtx | None:
    for ctx in contexts:
        if ctx.name == name:
            return ctx
    return None


def _extend(examples: list[Example], batch: list[Example]) -> int:
    examples.extend(batch)
    return len(examples)


# ---------------------------------------------------------------------------
# Example templates
# ---------------------------------------------------------------------------


def _lookup_examples(ctx: _TableCtx, seq: int, *, top_n: int = 10, suffix: str = "") -> list[Example]:
    if not ctx.pk_cols or not ctx.label_col:
        return []
    seq += 1
    cols = ", ".join([*ctx.pk_cols[:2], ctx.label_col])
    sql = (
        f"SELECT TOP {top_n} {cols}\n"
        f"FROM {ctx.qualified}\n"
        f"ORDER BY {ctx.label_col};"
    )
    return [Example(
        id=f"ex_{ctx.slug}_lookup_top{top_n}{suffix}",
        question_en=f"Show the first {top_n} rows from {ctx.name}.",
        question_ar=f"أعرض أول {top_n} سجلات من جدول {ctx.name}.",
        intent="lookup",
        difficulty=Difficulty.simple,
        required_tables=[ctx.name],
        required_columns=[*ctx.pk_cols[:1], ctx.label_col],
        sql=sql,
        explanation=f"Returns up to {top_n} rows from {ctx.name} ordered by {ctx.label_col}.",
        confidence=Confidence.medium,
    )]


def _count_examples(ctx: _TableCtx, seq: int) -> list[Example]:
    seq += 1
    return [Example(
        id=f"ex_{ctx.slug}_count",
        question_en=f"How many rows are in {ctx.name}?",
        question_ar=f"كم عدد السجلات في {ctx.name}؟",
        intent="aggregation",
        difficulty=Difficulty.simple,
        required_tables=[ctx.name],
        sql=f"SELECT COUNT({ctx.pk_cols[0]}) AS RowCount\nFROM {ctx.qualified};",
        explanation=f"Counts all rows in {ctx.name}.",
        confidence=Confidence.medium,
    )]


def _group_examples(ctx: _TableCtx, seq: int) -> list[Example]:
    assert ctx.group_col
    seq += 1
    return [Example(
        id=f"ex_{ctx.slug}_group_by_{_slug(ctx.group_col)}",
        question_en=f"How many {ctx.name} rows per {ctx.group_col}?",
        question_ar=f"كم عدد سجلات {ctx.name} لكل {ctx.group_col}؟",
        intent="grouping",
        difficulty=Difficulty.medium,
        required_tables=[ctx.name],
        required_columns=[ctx.group_col],
        sql=(
            f"SELECT {ctx.group_col}, COUNT({ctx.pk_cols[0]}) AS Cnt\n"
            f"FROM {ctx.qualified}\n"
            f"GROUP BY {ctx.group_col}\n"
            f"ORDER BY Cnt DESC;"
        ),
        explanation=f"Groups {ctx.name} by {ctx.group_col}.",
        confidence=Confidence.medium,
    )]


def _latest_examples(ctx: _TableCtx, seq: int) -> list[Example]:
    assert ctx.date_col and ctx.pk_cols
    seq += 1
    cols = ", ".join([*ctx.pk_cols[:1], ctx.date_col])
    return [Example(
        id=f"ex_{ctx.slug}_latest_by_{_slug(ctx.date_col)}",
        question_en=f"What are the most recent {ctx.name} records?",
        question_ar=f"ما أحدث سجلات {ctx.name}؟",
        intent="latest_records",
        difficulty=Difficulty.medium,
        required_tables=[ctx.name],
        required_columns=[ctx.date_col, *ctx.pk_cols[:1]],
        sql=(
            f"SELECT TOP 10 {cols}\n"
            f"FROM {ctx.qualified}\n"
            f"ORDER BY {ctx.date_col} DESC;"
        ),
        explanation=f"Latest {ctx.name} by {ctx.date_col}.",
        confidence=Confidence.medium,
    )]


def _trend_examples(ctx: _TableCtx, seq: int) -> list[Example]:
    assert ctx.date_col and ctx.pk_cols
    seq += 1
    return [Example(
        id=f"ex_{ctx.slug}_monthly_trend",
        question_en=f"Monthly row counts for {ctx.name}.",
        question_ar=f"اتجاه شهري لعدد سجلات {ctx.name}.",
        intent="trends",
        difficulty=Difficulty.analytical,
        required_tables=[ctx.name],
        required_columns=[ctx.date_col],
        sql=(
            f"SELECT YEAR({ctx.date_col}) AS Y, MONTH({ctx.date_col}) AS M, "
            f"COUNT({ctx.pk_cols[0]}) AS Cnt\n"
            f"FROM {ctx.qualified}\n"
            f"WHERE {ctx.date_col} IS NOT NULL\n"
            f"GROUP BY YEAR({ctx.date_col}), MONTH({ctx.date_col})\n"
            f"ORDER BY Y, M;"
        ),
        explanation=f"Monthly aggregation on {ctx.date_col}.",
        confidence=Confidence.low,
    )]


def _filter_examples(ctx: _TableCtx, seq: int) -> list[Example]:
    assert ctx.group_col and ctx.label_col and ctx.pk_cols
    seq += 1
    return [Example(
        id=f"ex_{ctx.slug}_filter_{_slug(ctx.group_col)}",
        question_en=f"List {ctx.name} where {ctx.group_col} is not null.",
        question_ar=f"اعرض {ctx.name} حيث {ctx.group_col} غير فارغ.",
        intent="filtering",
        difficulty=Difficulty.simple,
        required_tables=[ctx.name],
        required_columns=[ctx.group_col, ctx.label_col],
        sql=(
            f"SELECT TOP 100 {ctx.pk_cols[0]}, {ctx.label_col}, {ctx.group_col}\n"
            f"FROM {ctx.qualified}\n"
            f"WHERE {ctx.group_col} IS NOT NULL\n"
            f"ORDER BY {ctx.label_col};"
        ),
        explanation=f"Filtered lookup on {ctx.group_col}.",
        confidence=Confidence.medium,
    )]


def _join_examples(
    child: _TableCtx,
    parent: _TableCtx,
    rel: Relationship,
    seq: int,
) -> list[Example]:
    if not child.pk_cols or not parent.label_col:
        return []
    join_col = rel.from_columns[0]
    ref_col = rel.to_columns[0]
    parent_label = parent.label_col
    seq += 1
    alias_c, alias_p = "c", "p"
    return [Example(
        id=f"ex_{child.slug}_join_{parent.slug}",
        question_en=f"How many {child.name} rows per {parent.name}?",
        question_ar=f"كم سجل في {child.name} لكل {parent.name}؟",
        intent="join",
        difficulty=Difficulty.medium,
        required_tables=[child.name, parent.name],
        required_columns=[join_col, ref_col, parent_label],
        sql=(
            f"SELECT {alias_p}.{parent_label}, COUNT({alias_c}.{child.pk_cols[0]}) AS Cnt\n"
            f"FROM {child.qualified} AS {alias_c}\n"
            f"INNER JOIN {parent.qualified} AS {alias_p}\n"
            f"  ON {alias_p}.{ref_col} = {alias_c}.{join_col}\n"
            f"GROUP BY {alias_p}.{parent_label}\n"
            f"ORDER BY Cnt DESC;"
        ),
        explanation=f"Join {child.name} → {parent.name} on FK.",
        confidence=Confidence.medium,
    ), Example(
        id=f"ex_{child.slug}_rank_{parent.slug}",
        question_en=f"Top 10 {parent.name} by number of {child.name} rows.",
        question_ar=f"أعلى 10 {parent.name} حسب عدد سجلات {child.name}.",
        intent="ranking",
        difficulty=Difficulty.advanced,
        required_tables=[child.name, parent.name],
        sql=(
            f"SELECT TOP 10 {alias_p}.{parent_label}, COUNT(*) AS Cnt\n"
            f"FROM {child.qualified} AS {alias_c}\n"
            f"INNER JOIN {parent.qualified} AS {alias_p}\n"
            f"  ON {alias_p}.{ref_col} = {alias_c}.{join_col}\n"
            f"GROUP BY {alias_p}.{parent_label}\n"
            f"ORDER BY Cnt DESC;"
        ),
        explanation="Ranking parents by child row count.",
        confidence=Confidence.medium,
    )]


def _rejected_examples(profile: Profile, seq: int) -> list[Example]:
    """Examples that must be blocked by SQL policy (difficulty=rejected)."""
    schema = profile.meta.default_schema
    first_table = profile.database_schema.tables[0].name if profile.database_schema.tables else "Customers"
    qtable = _qualify(schema, first_table)
    templates = [
        (
            "delete_all",
            "احذف كل السجلات",
            "Delete all rows",
            f"DELETE FROM {qtable};",
            "destructive",
        ),
        (
            "select_star",
            "أعطني كل الأعمدة",
            "Select all columns with star",
            f"SELECT * FROM {qtable};",
            "select_star",
        ),
        (
            "sys_tables",
            "اعرض sys.tables",
            "List sys.tables",
            "SELECT name FROM sys.tables;",
            "blocked_schema",
        ),
        (
            "drop_table",
            "أسقط الجدول",
            "Drop the table",
            f"DROP TABLE {qtable};",
            "ddl",
        ),
        (
            "multi_statement",
            "استعلامان معاً",
            "Run two statements",
            "SELECT 1; SELECT 2;",
            "multi_statement",
        ),
    ]
    out: list[Example] = []
    for key, ar, en, sql, intent in templates:
        seq += 1
        out.append(Example(
            id=f"ex_reject_{key}",
            question_ar=ar,
            question_en=en,
            intent=intent,
            difficulty=Difficulty.rejected,
            required_tables=[first_table] if key not in ("sys_tables", "multi_statement") else [],
            sql=sql,
            explanation="Must be rejected by SQL policy before execution.",
            safety_notes=["Training example: agent must refuse or policy must block."],
            confidence=Confidence.high,
        ))
    return out
