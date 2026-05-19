"""Extract VAI structured SQL markers from Vanna poll ``raw`` payloads."""

from __future__ import annotations

from vai_agent.api.v1.chat import _extract_last_vai_structured_sql


def test_extract_last_vai_structured_reads_dataframe_chunk() -> None:
    raw = {
        "chunks": [
            {
                "rich": {
                    "type": "dataframe",
                    "data": {
                        "columns": ["CustomerID", "TotalSales"],
                        "data": [
                            {"CustomerID": 1, "TotalSales": 10.5},
                            {"CustomerID": 2, "TotalSales": 20.0},
                        ],
                        "column_types": {
                            "_vai_sql": "SELECT TOP 2 CustomerID, TotalSales FROM dbo.Customers",
                            "_vai_ms": "42",
                            "_vai_truncated": "0",
                        },
                    },
                },
            },
        ],
    }
    s = _extract_last_vai_structured_sql(raw)
    assert s is not None
    assert s["sql"].startswith("SELECT")
    assert s["row_count"] == 2
    assert s["columns"] == ["CustomerID", "TotalSales"]
    assert s["execution_ms"] == 42
    assert s["truncated"] is False


def test_extract_returns_none_without_marker() -> None:
    raw = {"chunks": [{"rich": {"type": "dataframe", "data": {"columns": ["a"], "data": [{"a": 1}]}}}]}
    assert _extract_last_vai_structured_sql(raw) is None
