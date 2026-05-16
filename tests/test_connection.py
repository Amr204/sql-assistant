"""Tests for :mod:`vai_agent.db.connection`.

All tests are offline — no real SQL Server is required.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vai_agent.db.connection import ConnectionSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal(**overrides: object) -> ConnectionSettings:
    kwargs: dict[str, object] = dict(host="host", database="db", username="user", password="pass")
    kwargs.update(overrides)
    return ConnectionSettings(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_port_default(self) -> None:
        s = _minimal()
        assert s.port == 1433

    def test_driver_default(self) -> None:
        s = _minimal()
        assert "SQL Server" in s.driver

    def test_trust_cert_default_is_false(self) -> None:
        s = _minimal()
        assert s.trust_server_certificate is False

    def test_connection_timeout_default(self) -> None:
        s = _minimal()
        assert s.connection_timeout == 10


# ---------------------------------------------------------------------------
# Connection string building
# ---------------------------------------------------------------------------

class TestBuildConnectionString:
    def test_contains_required_keys(self) -> None:
        s = _minimal()
        cs = s.build_connection_string()
        assert "SERVER=" in cs
        assert "DATABASE=" in cs
        assert "UID=" in cs
        assert "PWD=" in cs
        assert "ApplicationIntent=ReadOnly" in cs

    def test_trust_cert_yes_when_enabled(self) -> None:
        s = _minimal(trust_server_certificate=True)
        cs = s.build_connection_string()
        assert "TrustServerCertificate=Yes" in cs

    def test_trust_cert_no_when_disabled(self) -> None:
        s = _minimal()
        cs = s.build_connection_string()
        assert "TrustServerCertificate=No" in cs

    def test_port_included(self) -> None:
        s = _minimal(port=1234)
        cs = s.build_connection_string()
        assert "1234" in cs

    def test_password_is_in_connection_string(self) -> None:
        s = _minimal(password="my_secret_pw")
        cs = s.build_connection_string()
        assert "my_secret_pw" in cs

    def test_application_intent_always_readonly(self) -> None:
        s = _minimal()
        cs = s.build_connection_string()
        assert "ApplicationIntent=ReadOnly" in cs


# ---------------------------------------------------------------------------
# safe_repr — no password
# ---------------------------------------------------------------------------

class TestSafeRepr:
    def test_no_password_in_repr(self) -> None:
        s = _minimal(password="super_secret")
        assert "super_secret" not in s.safe_repr()

    def test_host_in_repr(self) -> None:
        s = _minimal(host="my-sql.internal")
        assert "my-sql.internal" in s.safe_repr()

    def test_database_in_repr(self) -> None:
        s = _minimal(database="SalesDB")
        assert "SalesDB" in s.safe_repr()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_port_too_high(self) -> None:
        with pytest.raises(ValidationError):
            _minimal(port=99999)

    def test_invalid_port_zero(self) -> None:
        with pytest.raises(ValidationError):
            _minimal(port=0)

    def test_invalid_driver_name(self) -> None:
        with pytest.raises(ValidationError, match="ODBC Driver"):
            _minimal(driver="Some Random Driver")

    def test_valid_driver_17(self) -> None:
        s = _minimal(driver="ODBC Driver 17 for SQL Server")
        assert "17" in s.driver

    def test_valid_driver_18(self) -> None:
        s = _minimal(driver="ODBC Driver 18 for SQL Server")
        assert "18" in s.driver


# ---------------------------------------------------------------------------
# SecretStr — password is hidden in repr
# ---------------------------------------------------------------------------

class TestSecretStr:
    def test_password_hidden_in_field_repr(self) -> None:
        s = _minimal(password="topsecret")
        assert "topsecret" not in str(s.password)
        assert "topsecret" not in repr(s)

    def test_get_secret_value_returns_plain_text(self) -> None:
        s = _minimal(password="topsecret")
        assert s.password.get_secret_value() == "topsecret"
