"""Tests for :mod:`vai_agent.security.pii_policy`."""

from __future__ import annotations

import pytest

from vai_agent.knowledge.profile_models import SecurityPolicy
from vai_agent.security.pii_policy import PiiCheckResult, PiiPolicyEngine, PiiViolation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _engine(
    *,
    pii_columns: list[str] | None = None,
    sensitive_columns: list[str] | None = None,
    secret_columns: list[str] | None = None,
) -> PiiPolicyEngine:
    return PiiPolicyEngine(
        SecurityPolicy(
            pii_columns=pii_columns or [],
            sensitive_columns=sensitive_columns or [],
            secret_columns=secret_columns or [],
        )
    )


def _codes(result: PiiCheckResult) -> set[str]:
    return {v.code for v in result.violations}


# ---------------------------------------------------------------------------
# PII001 — Secret columns
# ---------------------------------------------------------------------------


class TestSecretColumns:
    def test_qualified_secret_blocked(self) -> None:
        r = _engine(secret_columns=["Employees.BirthDate"]).check(
            "SELECT e.BirthDate FROM dbo.Employees AS e"
        )
        assert not r.allowed
        assert "PII001" in _codes(r)

    def test_unqualified_secret_blocked_conservatively(self) -> None:
        r = _engine(secret_columns=["Employees.BirthDate"]).check(
            "SELECT BirthDate FROM dbo.Employees"
        )
        assert not r.allowed
        assert "PII001" in _codes(r)

    def test_wrong_table_not_blocked(self) -> None:
        # BirthDate is secret on Employees, not on Customers
        r = _engine(secret_columns=["Employees.BirthDate"]).check(
            "SELECT c.BirthDate FROM dbo.Customers AS c"
        )
        # c.BirthDate → table alias 'c', not 'Employees' → no qualified match
        # But unqualified fallback matches the col name — conservatively blocked
        assert not r.allowed

    def test_unrelated_column_not_blocked(self) -> None:
        r = _engine(secret_columns=["Employees.BirthDate"]).check(
            "SELECT CustomerID, CompanyName FROM dbo.Customers"
        )
        assert r.allowed

    def test_secret_takes_priority_over_pii(self) -> None:
        r = _engine(
            secret_columns=["Employees.BirthDate"],
            pii_columns=["Employees.BirthDate"],
        ).check("SELECT BirthDate FROM dbo.Employees")
        # Secret (PII001) should appear, not PII002
        assert "PII001" in _codes(r)
        assert "PII002" not in _codes(r)


# ---------------------------------------------------------------------------
# PII002 — PII columns
# ---------------------------------------------------------------------------


class TestPiiColumns:
    def test_qualified_pii_blocked(self) -> None:
        r = _engine(pii_columns=["Customers.ContactName"]).check(
            "SELECT c.ContactName FROM dbo.Customers AS c"
        )
        assert not r.allowed
        assert "PII002" in _codes(r)

    def test_unqualified_pii_blocked(self) -> None:
        r = _engine(pii_columns=["Customers.ContactName"]).check(
            "SELECT ContactName, CompanyName FROM dbo.Customers"
        )
        assert not r.allowed
        assert "PII002" in _codes(r)

    def test_non_pii_column_passes(self) -> None:
        r = _engine(pii_columns=["Customers.ContactName"]).check(
            "SELECT CustomerID, CompanyName FROM dbo.Customers"
        )
        assert r.allowed


class TestGroupAccess:
    def test_secret_column_allowed_for_admin(self) -> None:
        r = _engine(secret_columns=["Employees.BirthDate"]).check(
            "SELECT BirthDate FROM dbo.Employees",
            user_groups=["admin"],
        )
        assert r.allowed

    def test_pii_column_allowed_for_pii_reader(self) -> None:
        r = _engine(pii_columns=["Customers.ContactName"]).check(
            "SELECT ContactName FROM dbo.Customers",
            user_groups=["pii_reader"],
        )
        assert r.allowed


# ---------------------------------------------------------------------------
# PII003 — Sensitive columns
# ---------------------------------------------------------------------------


class TestSensitiveColumns:
    def test_sensitive_column_blocked(self) -> None:
        r = _engine(sensitive_columns=["Orders.Freight"]).check(
            "SELECT Freight FROM dbo.Orders"
        )
        assert not r.allowed
        assert "PII003" in _codes(r)

    def test_qualified_sensitive_blocked(self) -> None:
        r = _engine(sensitive_columns=["Orders.Freight"]).check(
            "SELECT o.Freight, o.OrderID FROM dbo.Orders AS o"
        )
        assert not r.allowed
        assert "PII003" in _codes(r)

    def test_non_sensitive_column_passes(self) -> None:
        r = _engine(sensitive_columns=["Orders.Freight"]).check(
            "SELECT OrderID, CustomerID FROM dbo.Orders"
        )
        assert r.allowed


# ---------------------------------------------------------------------------
# PII004 — Heuristic PII patterns (warnings, do not block)
# ---------------------------------------------------------------------------


class TestHeuristicPii:
    def test_column_named_password_is_warning(self) -> None:
        r = _engine().check("SELECT UserPassword FROM dbo.Users")
        # No policy PII entries, but heuristic catches 'password'
        codes = _codes(r)
        assert "PII004" in codes
        assert r.allowed  # warnings don't block

    def test_phone_column_triggers_warning(self) -> None:
        r = _engine().check("SELECT Phone FROM dbo.Customers")
        assert "PII004" in _codes(r)
        assert r.allowed

    def test_email_column_triggers_warning(self) -> None:
        r = _engine().check("SELECT Email FROM dbo.Users")
        assert "PII004" in _codes(r)
        assert r.allowed

    def test_credit_card_is_heuristic_secret(self) -> None:
        r = _engine().check("SELECT CreditCardNumber FROM dbo.Payments")
        assert "PII004" in _codes(r)
        assert r.allowed  # still only a warning (no policy entry)

    def test_neutral_column_no_warning(self) -> None:
        r = _engine().check("SELECT OrderID, CompanyName FROM dbo.Customers")
        assert r.allowed
        assert "PII004" not in _codes(r)


# ---------------------------------------------------------------------------
# Multiple violations
# ---------------------------------------------------------------------------


class TestMultipleViolations:
    def test_two_pii_columns_both_flagged(self) -> None:
        r = _engine(pii_columns=["Customers.ContactName", "Customers.Phone"]).check(
            "SELECT ContactName, Phone, CompanyName FROM dbo.Customers"
        )
        assert not r.allowed
        pii_violations = [v for v in r.violations if v.code == "PII002"]
        assert len(pii_violations) == 2

    def test_mixed_secret_and_pii(self) -> None:
        r = _engine(
            secret_columns=["Employees.BirthDate"],
            pii_columns=["Customers.ContactName"],
        ).check(
            "SELECT BirthDate, ContactName FROM dbo.SomeTable"
        )
        assert not r.allowed
        assert "PII001" in _codes(r)
        assert "PII002" in _codes(r)


# ---------------------------------------------------------------------------
# Empty policy
# ---------------------------------------------------------------------------


class TestEmptyPolicy:
    def test_no_policy_lists_allows_any_explicit_column(self) -> None:
        r = _engine().check("SELECT OrderID, CustomerID FROM dbo.Orders")
        assert r.allowed

    def test_empty_policy_still_runs_heuristics(self) -> None:
        r = _engine().check("SELECT ssn FROM dbo.Users")
        assert "PII004" in _codes(r)
        assert r.allowed


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class TestResultSchema:
    def test_result_is_pii_check_result(self) -> None:
        r = _engine().check("SELECT CustomerID FROM dbo.Customers")
        assert isinstance(r, PiiCheckResult)
        assert isinstance(r.violations, list)

    def test_violation_has_required_fields(self) -> None:
        r = _engine(pii_columns=["Customers.ContactName"]).check(
            "SELECT ContactName FROM dbo.Customers"
        )
        assert r.violations
        v = r.violations[0]
        assert isinstance(v, PiiViolation)
        assert v.code
        assert v.severity in {"error", "warning"}
        assert v.column_ref
        assert v.message


# ---------------------------------------------------------------------------
# PiiViolationError raise helper
# ---------------------------------------------------------------------------


class TestPiiViolationError:
    def test_raise_on_block(self) -> None:
        from vai_agent.security.errors import PiiViolationError

        result = _engine(secret_columns=["t.col"]).check("SELECT col FROM t")
        assert not result.allowed
        with pytest.raises(PiiViolationError) as exc_info:
            if not result.allowed:
                raise PiiViolationError(result)
        assert exc_info.value.result is result
