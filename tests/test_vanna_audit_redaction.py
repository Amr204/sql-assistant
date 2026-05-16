"""Vanna audit JSON must not embed raw SQL."""

from __future__ import annotations

from vai_agent.vanna_integration.vanna_audit import redact_audit_payload


def test_vanna_audit_redacts_sql() -> None:
    payload = {"parameters": {"sql": "SELECT TOP 10 CustomerID FROM dbo.Customers"}}
    clean = redact_audit_payload(payload)

    assert "SELECT TOP 10" not in str(clean)
    assert "[REDACTED_SQL]" in str(clean)
    assert "sql_hash" in str(clean)


def test_redact_payload_alias_matches_audit_payload() -> None:
    from vai_agent.vanna_integration.vanna_audit import redact_payload

    payload = {"tool": "run_sql", "parameters": {"sql": "SELECT 1"}}
    redacted = redact_payload(payload)
    assert "SELECT 1" not in str(redacted)
    assert "[REDACTED_SQL]" in str(redacted)
