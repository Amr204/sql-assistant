"""Vanna :class:`~vanna.core.audit.base.AuditLogger` with JSONL sink and SQL redaction."""

from __future__ import annotations

import hashlib
from typing import Any

from vanna.core.audit import AuditLogger
from vanna.core.audit.models import AuditEvent

from vai_agent.security import audit_log as app_audit

_SECRET_KEYS = frozenset(
    {
        "sql",
        "query",
        "database_url",
        "connection_string",
        "password",
        "api_key",
        "authorization",
        "token",
    },
)


def _hash_sql(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact_audit_payload(obj: Any) -> Any:
    """Return a deep-copied structure safe for logging (SQL and secrets redacted)."""

    if isinstance(obj, dict):
        clean: dict[str, Any] = {}
        for key, value in obj.items():
            lk = str(key).lower()

            if lk == "sql" and isinstance(value, str):
                clean["sql_hash"] = _hash_sql(value)
                clean[key] = "[REDACTED_SQL]"
                continue

            if lk in _SECRET_KEYS:
                clean[key] = "[REDACTED]"
                continue

            clean[key] = redact_audit_payload(value)
        return clean

    if isinstance(obj, list):
        return [redact_audit_payload(v) for v in obj]

    return obj


# Alias used by tests and external callers
redact_payload = redact_audit_payload


class JsonlVannaAuditLogger(AuditLogger):
    """Serialises Vanna audit events via :mod:`vai_agent.security.audit_log` (redacted)."""

    async def log_event(self, event: AuditEvent) -> None:
        """Log event."""
        payload = event.model_dump(mode="json")
        safe_payload = redact_audit_payload(payload)

        app_audit.emit_audit_record(
            {
                "kind": "vanna_audit",
                "event_type": safe_payload.get("event_type", type(event).__name__),
                "payload": safe_payload,
            },
        )

    async def query_events(self, *args: object, **kwargs: object) -> list[AuditEvent]:
        """Query events."""
        return []
