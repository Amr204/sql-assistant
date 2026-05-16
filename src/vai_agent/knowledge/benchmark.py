"""Static benchmark checks for profile examples and eval questions.

Used by ``scripts/benchmark_questions.py`` to produce
``reports/benchmark_results.json`` and ``reports/benchmark_report.md``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import sqlglot
import sqlglot.errors
import sqlglot.expressions as exp
from pydantic import BaseModel, ConfigDict, Field

from vai_agent.knowledge.profile_models import (
    EvalQuestion,
    Example,
    Profile,
)
from vai_agent.security.pii_policy import PiiPolicyEngine
from vai_agent.security.sql_policy import SqlPolicyEngine

logger = logging.getLogger(__name__)

SourceKind = Literal["examples", "eval_questions"]


class BenchmarkCheck(BaseModel):
    """Outcome of a single static check."""

    model_config = ConfigDict(frozen=True)

    code: str
    passed: bool
    severity: Literal["error", "warning", "info"]
    message: str


class BenchmarkItemResult(BaseModel):
    """Benchmark outcome for one example or eval question."""

    model_config = ConfigDict(frozen=True)

    id: str
    passed: bool
    checks: list[BenchmarkCheck] = Field(default_factory=list)
    question_en: str | None = None
    question_ar: str | None = None


class BenchmarkReport(BaseModel):
    """Aggregate benchmark output."""

    profile_id: str
    source: SourceKind
    generated_at: str
    summary: dict[str, int]
    results: list[BenchmarkItemResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public runners
# ---------------------------------------------------------------------------


def benchmark_examples(profile: Profile) -> BenchmarkReport:
    """Run all static checks against ``profile.examples``."""
    sql_engine = SqlPolicyEngine(profile.security_policy)
    pii_engine = PiiPolicyEngine(profile.security_policy)
    results: list[BenchmarkItemResult] = []

    for ex in profile.examples.examples:
        checks = _check_example(profile, ex, sql_engine, pii_engine)
        results.append(BenchmarkItemResult(
            id=ex.id,
            passed=all(c.passed for c in checks if c.severity == "error"),
            checks=checks,
            question_en=ex.question_en,
            question_ar=ex.question_ar,
        ))

    return _build_report(profile.meta.profile_id, "examples", results)


def benchmark_eval_questions(profile: Profile) -> BenchmarkReport:
    """Validate eval questions (reference SQL when present)."""
    sql_engine = SqlPolicyEngine(profile.security_policy)
    pii_engine = PiiPolicyEngine(profile.security_policy)
    results: list[BenchmarkItemResult] = []

    for q in profile.eval_questions.questions:
        checks = _check_eval_question(profile, q, sql_engine, pii_engine)
        results.append(BenchmarkItemResult(
            id=q.id,
            passed=all(c.passed for c in checks if c.severity == "error"),
            checks=checks,
            question_en=q.question_en,
            question_ar=q.question_ar,
        ))

    return _build_report(profile.meta.profile_id, "eval_questions", results)


def write_benchmark_reports(
    report: BenchmarkReport,
    *,
    reports_dir: Path,
) -> tuple[Path, Path]:
    """Write JSON + Markdown reports; return both paths."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "benchmark_results.json"
    md_path = reports_dir / "benchmark_report.md"

    json_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    logger.info(
        "benchmark reports written",
        extra={"json": str(json_path), "markdown": str(md_path)},
    )
    return json_path, md_path


# ---------------------------------------------------------------------------
# Per-item checks
# ---------------------------------------------------------------------------


def _check_example(
    profile: Profile,
    ex: Example,
    sql_engine: SqlPolicyEngine,
    pii_engine: PiiPolicyEngine,
) -> list[BenchmarkCheck]:
    checks: list[BenchmarkCheck] = []
    rejected = ex.difficulty.value == "rejected"

    checks.append(_check_bilingual(ex.question_ar, ex.question_en))

    if not ex.sql.strip():
        checks.append(BenchmarkCheck(
            code="BN009",
            passed=False,
            severity="error",
            message="SQL is empty.",
        ))
        return checks

    checks.extend(_check_sql(profile, ex.sql, ex.required_tables, sql_engine, pii_engine, rejected))
    return checks


def _check_eval_question(
    profile: Profile,
    q: EvalQuestion,
    sql_engine: SqlPolicyEngine,
    pii_engine: PiiPolicyEngine,
) -> list[BenchmarkCheck]:
    checks: list[BenchmarkCheck] = [_check_bilingual(q.question_ar, q.question_en)]

    for table in q.expected_tables:
        if not profile.database_schema.has_table(table):
            checks.append(BenchmarkCheck(
                code="BN010",
                passed=False,
                severity="error",
                message=f"expected_table {table!r} not in schema.",
            ))

    if q.reference_sql:
        checks.extend(
            _check_sql(
                profile,
                q.reference_sql,
                q.expected_tables,
                sql_engine,
                pii_engine,
                must_reject=q.must_reject,
            )
        )
    elif q.must_reject:
        checks.append(BenchmarkCheck(
            code="BN011",
            passed=True,
            severity="info",
            message="must_reject question without reference_sql (manual review).",
        ))

    return checks


def _check_bilingual(question_ar: str | None, question_en: str | None) -> BenchmarkCheck:
    ok = bool(question_ar and question_en)
    return BenchmarkCheck(
        code="BN008",
        passed=ok,
        severity="warning" if not ok else "info",
        message="Both question_ar and question_en are present."
        if ok
        else "Missing Arabic or English question text.",
    )


def _check_sql(
    profile: Profile,
    sql: str,
    required_tables: list[str],
    sql_engine: SqlPolicyEngine,
    pii_engine: PiiPolicyEngine,
    must_reject: bool,
) -> list[BenchmarkCheck]:
    checks: list[BenchmarkCheck] = []
    schema = profile.database_schema

    # BN001 — syntax
    try:
        statements = sqlglot.parse(sql, read="tsql")
        syntax_ok = bool(statements) and all(s is not None for s in statements)
        msg = "SQL parses as T-SQL."
    except sqlglot.errors.SqlglotError as exc:
        syntax_ok = False
        msg = f"Parse error: {exc}"
    checks.append(BenchmarkCheck(
        code="BN001",
        passed=syntax_ok,
        severity="error",
        message=msg,
    ))
    if not syntax_ok:
        return checks

    # BN002 / BN003 — tables & columns
    table_refs, column_refs = _extract_table_column_refs(sql)
    missing_tables = [t for t in table_refs if not schema.has_table(t)]
    if not must_reject:
        checks.append(BenchmarkCheck(
            code="BN002",
            passed=not missing_tables,
            severity="error",
            message="All referenced tables exist."
            if not missing_tables
            else f"Unknown tables: {missing_tables}",
        ))

    missing_cols: list[str] = []
    for table, column in column_refs:
        if table and column and not schema.has_column(table, column):
            missing_cols.append(f"{table}.{column}")
    checks.append(BenchmarkCheck(
        code="BN003",
        passed=not missing_cols,
        severity="warning" if missing_cols else "info",
        message="Column references resolve to schema."
        if not missing_cols
        else f"Unresolved columns: {missing_cols}",
    ))

    # BN004 — SQL policy
    policy_result = sql_engine.validate(sql)
    if must_reject:
        policy_ok = not policy_result.allowed
        policy_msg = (
            "Policy correctly blocks rejected example."
            if policy_ok
            else "Rejected example was allowed by policy."
        )
    else:
        policy_ok = policy_result.allowed
        codes = [v.code for v in policy_result.violations]
        policy_msg = "Policy allows example." if policy_ok else f"Policy blocked: {codes}"
    checks.append(BenchmarkCheck(
        code="BN004",
        passed=policy_ok,
        severity="error",
        message=policy_msg,
    ))

    # BN005 — PII (only for allowed examples)
    if not must_reject:
        pii_result = pii_engine.check(sql)
        pii_ok = pii_result.allowed
        checks.append(BenchmarkCheck(
            code="BN005",
            passed=pii_ok,
            severity="error",
            message="PII policy allows SQL."
            if pii_ok
            else f"PII blocked: {[v.code for v in pii_result.violations]}",
        ))

    # BN006 — required tables
    if required_tables:
        overlap = set(required_tables) & table_refs
        req_ok = bool(overlap) or not table_refs
        checks.append(BenchmarkCheck(
            code="BN006",
            passed=req_ok,
            severity="warning",
            message="SQL references at least one required_table."
            if req_ok
            else f"No overlap with required_tables {required_tables}.",
        ))

    # BN007 — join when multiple tables required
    if len(required_tables) >= 2 and not must_reject:
        join_ok = len(table_refs) >= 2 and (
            "join" in sql.lower() or len(table_refs) >= len(required_tables)
        )
        checks.append(BenchmarkCheck(
            code="BN007",
            passed=join_ok,
            severity="warning",
            message="Multi-table SQL includes a join or references multiple tables."
            if join_ok
            else "Multiple required_tables but SQL may lack a join.",
        ))

    return checks


def _extract_table_column_refs(sql: str) -> tuple[set[str], set[tuple[str | None, str]]]:
    table_refs: set[str] = set()
    column_refs: set[tuple[str | None, str]] = set()
    try:
        for stmt in sqlglot.parse(sql, read="tsql"):
            if stmt is None:
                continue
            for node in stmt.walk():
                if isinstance(node, exp.Table):
                    if node.name:
                        table_refs.add(node.name)
                elif isinstance(node, exp.Column):
                    table_ref = node.table
                    if isinstance(table_ref, str):
                        table_name: str | None = table_ref
                    elif table_ref is not None:
                        table_name = table_ref.name
                    else:
                        table_name = None
                    column_refs.add((table_name, node.name))
    except sqlglot.errors.SqlglotError:
        pass
    return table_refs, column_refs


def _build_report(
    profile_id: str,
    source: SourceKind,
    results: list[BenchmarkItemResult],
) -> BenchmarkReport:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    warnings = sum(
        1
        for r in results
        for c in r.checks
        if c.severity == "warning" and not c.passed
    )
    return BenchmarkReport(
        profile_id=profile_id,
        source=source,
        generated_at=datetime.now(UTC).isoformat(),
        summary={
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
        },
        results=results,
    )


def _render_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Benchmark Report",
        "",
        f"- **Profile:** `{report.profile_id}`",
        f"- **Source:** `{report.source}`",
        f"- **Generated:** {report.generated_at}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Total  | {report.summary['total']} |",
        f"| Passed | {report.summary['passed']} |",
        f"| Failed | {report.summary['failed']} |",
        f"| Warnings | {report.summary.get('warnings', 0)} |",
        "",
        "## Failures",
        "",
    ]
    failures = [r for r in report.results if not r.passed]
    if not failures:
        lines.append("_No failures._")
    else:
        for item in failures:
            lines.append(f"### `{item.id}`")
            if item.question_en:
                lines.append(f"- **EN:** {item.question_en}")
            if item.question_ar:
                lines.append(f"- **AR:** {item.question_ar}")
            for check in item.checks:
                if not check.passed:
                    lines.append(f"- `{check.code}` ({check.severity}): {check.message}")
            lines.append("")

    lines.append("## Full results (JSON)")
    lines.append("")
    lines.append("See `benchmark_results.json` for machine-readable output.")
    return "\n".join(lines)
