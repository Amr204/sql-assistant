"""VAI-style presentation: separate narrative ``answer`` from structured ``SqlTable``."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from vai_agent.api.v1.schemas import SqlTable

_TABLE_FROM_SQL = re.compile(
    r"\bFROM\s+(?:\[?(?:dbo|DBO)\]?\.)?\[?([A-Za-z_][\w]*)\]?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PresentedSqlResult:
    """Structured chat presentation layer output."""

    answer: str
    sql: str | None
    explanation: str | None = None
    confidence: float | None = None
    table: SqlTable | None = None
    warnings: list[str] = field(default_factory=list)


def _table_label(sql: str | None) -> str:
    if not sql:
        return ""
    m = _TABLE_FROM_SQL.search(sql)
    return m.group(1) if m else ""


def _is_mostly_arabic(text: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in text)


def _arabic_ranking_summary(question: str, row_count: int) -> str | None:
    q = question.strip()
    m = re.search(
        r"(أفضل|افضل|أضعف|اضعف|أقوى|اقوى|top|best|bottom|lowest)\s*(\d+)",
        q,
        re.IGNORECASE,
    )
    n = int(m.group(2)) if m else row_count
    low = any(
        k in q
        for k in (
            "أضعف",
            "اضعف",
            "أسوأ",
            "اسوأ",
            "weakest",
            "lowest",
            "bottom",
        )
    )
    high = any(
        k in q
        for k in (
            "أفضل",
            "افضل",
            "أقوى",
            "اقوى",
            "best",
            "top",
            "strongest",
        )
    )
    if low:
        return f"هؤلاء هم أضعف {n} عملاء حسب إجمالي المبيعات."
    if high:
        return f"هؤلاء هم أفضل {n} عملاء حسب إجمالي المبيعات."
    return None


def _is_count_shape(columns: list[str], rows: list[dict[str, Any]], question: str) -> bool:
    if len(rows) != 1 or len(columns) != 1:
        return False
    col = columns[0].lower()
    if "count" in col or col in ("record_count", "cnt", "total"):
        return True
    q = question.lower()
    return "عدد" in question or "كم" in question or "count" in q or "how many" in q


def present_sql_result(
    *,
    question: str,
    sql: str | None,
    columns: list[str],
    rows: list[dict[str, Any]],
    row_count: int,
    execution_ms: int | None = None,
    truncated: bool = False,
) -> PresentedSqlResult:
    """Build ``answer`` + optional ``SqlTable`` without CSV / visualization / markdown tables in text."""

    _ = execution_ms  # reserved for future copy ("نُفّذ خلال …ms")
    tbl_name = _table_label(sql)
    arabic = _is_mostly_arabic(question)

    if _is_count_shape(columns, rows, question):
        col = columns[0]
        value = rows[0].get(col)
        if arabic:
            if tbl_name:
                answer = f"عدد السجلات في جدول {tbl_name} هو {value} سجلًا."
                explanation = "تم تنفيذ استعلام عدّ مباشر على الجدول المطلوب."
            else:
                answer = f"عدد السجلات هو {value} سجلًا."
                explanation = "تم تنفيذ استعلام عدّ مباشر."
        else:
            if tbl_name:
                answer = f"The row count for table {tbl_name} is {value}."
                explanation = "A direct COUNT query was executed on the requested table."
            else:
                answer = f"The result is {value}."
                explanation = "A direct COUNT query was executed."
        return PresentedSqlResult(
            answer=answer,
            sql=sql,
            explanation=explanation,
            confidence=0.95,
            table=None,
            warnings=[],
        )

    if not columns or not rows:
        msg = "لم تُرجع الاستعلام أي صفوف." if arabic else "The query returned no rows."
        return PresentedSqlResult(
            answer=msg,
            sql=sql,
            explanation="تم تنفيذ الاستعلام بنجاح دون نتائج مطابقة." if arabic else "SQL ran successfully with an empty result set.",
            confidence=0.9,
            table=None,
            warnings=[],
        )

    st = SqlTable(columns=columns, rows=rows, row_count=row_count, truncated=truncated)
    if arabic:
        summary = _arabic_ranking_summary(question, row_count)
        answer = summary if summary else f"تم إرجاع {row_count} سجلًا."
        explanation = "تم توليد SQL والتحقق منه ثم تنفيذ الاستعلام بنجاح. راجع الجدول للتفاصيل."
    else:
        answer = f"Returned {row_count} row(s)."
        explanation = "SQL was generated, validated, and executed successfully. See the table for details."
    return PresentedSqlResult(
        answer=answer,
        sql=sql,
        explanation=explanation,
        confidence=0.92,
        table=st,
        warnings=[],
    )


def clean_assistant_text(text: str) -> str:
    """Strip internal tool/export noise; prefer structured fields over this text."""

    if not text:
        return ""
    forbidden_markers = (
        "Results saved to file",
        "FOR VISUALIZE_DATA",
        "query_results_",
        "Test 1",
    )
    cleaned = text
    for marker in forbidden_markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker)[0].strip()

    lines_out: list[str] = []
    banned_line = (
        "results saved to file",
        "for visualize_data",
        "query_results_",
        "important: for visualize",
        "test 1",
        "test 2",
        "test 3",
        ".csv",
    )
    for line in cleaned.splitlines():
        lower = line.lower()
        if any(b in lower for b in banned_line):
            continue
        lines_out.append(line)
    return "\n".join(lines_out).strip()
