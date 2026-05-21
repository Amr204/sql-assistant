"""Structured chat presentation (VAI-style contract)."""

from __future__ import annotations

from vai_agent.api.v1.schemas import SqlTable
from vai_agent.config.settings import Settings
from vai_agent.presentation.sql_result_presenter import (
    clean_assistant_text,
    present_sql_result,
)


def test_clean_assistant_text_strips_internal_markers() -> None:
    raw = """Here is the answer.
Results saved to file: query_results_abc.csv
IMPORTANT: FOR VISUALIZE_DATA USE FILENAME query_results_abc.csv
Test 1 more text"""
    out = clean_assistant_text(raw)
    assert "Results saved to file" not in out
    assert "VISUALIZE_DATA" not in out
    assert "query_results_" not in out
    assert "Test 1" not in out


def test_clean_assistant_text_strips_query_results_in_suffix() -> None:
    out = clean_assistant_text("prefix query_results_x.csv suffix")
    assert "query_results_" not in out
    assert out.startswith("prefix")


def test_count_answer_not_csv_like() -> None:
    p = present_sql_result(
        question="كم عدد السجلات في Suppliers؟",
        sql="SELECT COUNT(*) AS [record_count] FROM dbo.Suppliers",
        columns=["record_count"],
        rows=[{"record_count": 29}],
        row_count=1,
        execution_ms=40,
        truncated=False,
    )
    assert "29" in p.answer
    assert "Suppliers" in p.answer
    assert "record_count" not in p.answer.lower()
    assert p.table is None
    assert p.sql and "[record_count]" in p.sql


def test_multi_row_returns_sql_table_not_markdown_string() -> None:
    rows = [
        {"CustomerID": 1, "CompanyName": "A", "TotalSales": 100.0},
        {"CustomerID": 2, "CompanyName": "B", "TotalSales": 200.0},
    ]
    p = present_sql_result(
        question="اعرض أفضل العملاء",
        sql="SELECT TOP 5 ...",
        columns=["CustomerID", "CompanyName", "TotalSales"],
        rows=rows,
        row_count=2,
        execution_ms=80,
        truncated=False,
    )
    assert isinstance(p.table, SqlTable)
    assert p.table.row_count == 2
    assert "|" not in p.answer
    assert "CustomerID" not in p.answer
    assert p.table.columns[0] == "CustomerID"


def test_arabic_ranking_summary_for_weak_customers() -> None:
    rows = [{"CustomerID": i, "TotalSales": float(i)} for i in range(1, 6)]
    p = present_sql_result(
        question="اعرض أضعف 5 عملاء حسب إجمالي المبيعات",
        sql="SELECT TOP 5 ...",
        columns=["CustomerID", "TotalSales"],
        rows=rows,
        row_count=5,
        truncated=False,
    )
    assert "أضعف" in p.answer
    assert "5" in p.answer
    assert "|" not in p.answer
    assert p.table is not None


def test_settings_chunking_strategy_defaults_to_early(monkeypatch) -> None:
    monkeypatch.delenv("CHUNKING_STRATEGY", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.chunking_strategy == "early"
