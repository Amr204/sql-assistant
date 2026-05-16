"""Database connection settings and pyodbc connection-string builder.

All configuration is loaded from environment variables (or a ``.env``
file) via :class:`ConnectionSettings`. Nothing in this module opens an
actual connection; that responsibility belongs to :mod:`mssql_runner`.

Connection string format used
------------------------------
We build an ODBC DSN-less connection string so the application works on
any machine that has the *ODBC Driver 17/18 for SQL Server* installed,
without requiring a pre-configured DSN::

    DRIVER={ODBC Driver 18 for SQL Server};
    SERVER=<host>,<port>;
    DATABASE=<database>;
    UID=<username>;
    PWD=<password>;
    TrustServerCertificate=Yes|No;
    Connection Timeout=<seconds>;
    ApplicationIntent=ReadOnly;

``ApplicationIntent=ReadOnly`` is always appended.  When the target
server is configured with an Always On Availability Group, this routes
the connection to a readable secondary. On a standalone instance it is
accepted but has no routing effect.

Secrets
-------
``db_password`` is stored as ``pydantic.SecretStr``.  Callers must call
``.get_secret_value()`` explicitly — the string representation of the
field never reveals the password, preventing accidental log leaks.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Supported ODBC driver names. The user can add others by overriding the
# ``db_driver`` environment variable.
_VALID_DRIVER_RE = re.compile(
    r"^ODBC Driver \d+ for SQL Server$", re.IGNORECASE
)


class ConnectionSettings(BaseSettings):
    """SQL Server connection parameters.

    All fields are read from environment variables (case-insensitive).
    Copy ``.env.example`` to ``.env`` and fill in the values before
    running the application.

    The password is kept as a ``SecretStr`` so it never appears in logs
    or repr output.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Prefix avoids collisions with generic env vars.
        env_prefix="DB_",
    )

    host: str = Field(description="SQL Server hostname or IP address.")
    port: int = Field(default=1433, ge=1, le=65535, description="TCP port.")
    database: str = Field(description="Target database name.")
    username: str = Field(description="SQL login username (read-only user recommended).")
    password: SecretStr = Field(description="SQL login password.")
    driver: str = Field(
        default="ODBC Driver 18 for SQL Server",
        description="ODBC driver name as it appears in odbcinst.ini / registry.",
    )
    trust_server_certificate: bool = Field(
        default=False,
        description=(
            "Set to True in dev/staging environments with self-signed certificates. "
            "Must be False in production."
        ),
    )
    connection_timeout: int = Field(
        default=10,
        ge=1,
        description="Seconds to wait while establishing the connection.",
    )
    # ApplicationIntent is always ReadOnly — not user-configurable to prevent
    # accidental write access.
    _application_intent: Literal["ReadOnly"] = "ReadOnly"

    @field_validator("driver")
    @classmethod
    def _driver_looks_like_sql_server(cls, v: str) -> str:
        if not _VALID_DRIVER_RE.match(v.strip()):
            raise ValueError(
                f"db_driver {v!r} does not match the expected pattern "
                f"'ODBC Driver N for SQL Server'. Update the value if you "
                f"have a non-standard driver name."
            )
        return v.strip()

    def build_connection_string(self) -> str:
        """Return a pyodbc ODBC connection string.

        The password is retrieved via ``SecretStr.get_secret_value()`` so
        it is only exposed at the moment the connection is actually opened.
        The returned string must **not** be logged.
        """
        trust = "Yes" if self.trust_server_certificate else "No"
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password.get_secret_value()};"
            f"TrustServerCertificate={trust};"
            f"Connection Timeout={self.connection_timeout};"
            f"ApplicationIntent=ReadOnly;"
        )

    def safe_repr(self) -> str:
        """Return a connection description safe for logging (no password)."""
        return (
            f"sqlserver://{self.username}@{self.host}:{self.port}"
            f"/{self.database} driver={self.driver!r}"
        )


@lru_cache(maxsize=1)
def get_connection_settings() -> ConnectionSettings:
    """Return the cached :class:`ConnectionSettings` for this process."""
    return ConnectionSettings()  # type: ignore[call-arg]
