"""Structured audit logging for chat, LLM, and tool/SQL paths.

Writes JSON lines to ``.data/audit/audit.jsonl`` (configurable).  Callers
must avoid logging raw secrets, full connection strings, or complete SQL
when policy marks the request sensitive — prefer :func:`sql_fingerprint`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from logging.handlers import RotatingFileHandler
from collections.abc import Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(".data") / "audit" / "audit.jsonl"
_AUDIT_MAX_BYTES = 20 * 1024 * 1024
_AUDIT_BACKUP_COUNT = 10


def sql_fingerprint(sql: str) -> str:
    """Return a stable short hash of *sql* for audit correlation."""

    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def emit_audit_record(
    record: Mapping[str, Any],
    *,
    path: Path | None = None,
) -> str:
    """Append one JSON object to the audit log; returns *audit_id*."""

    audit_id = str(record.get("audit_id") or uuid.uuid4())
    row = {**dict(record), "audit_id": audit_id, "ts_ms": int(time.time() * 1000)}
    target = path or _DEFAULT_PATH
    _ensure_parent(target)
    line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
    try:
        _append_audit_line(target, line)
    except OSError as exc:
        logger.warning("audit write failed", extra={"exc_type": type(exc).__name__})
    return audit_id


def _audit_logger_for(path: Path) -> logging.Logger:
    """Return a dedicated logger with a rotating handler for *path*."""

    key = str(path.resolve())
    audit_logger = logging.getLogger(f"vai_agent.audit.jsonl.{key}")
    if not audit_logger.handlers:
        handler = RotatingFileHandler(
            key,
            maxBytes=_AUDIT_MAX_BYTES,
            backupCount=_AUDIT_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)
        audit_logger.propagate = False
        audit_logger.setLevel(logging.INFO)
    return audit_logger


def _append_audit_line(path: Path, line: str) -> None:
    """Append one JSON line via a rotating file handler."""

    _ensure_parent(path)
    _audit_logger_for(path).info(line.rstrip("\n"))


def emit_tool_audit(
    *,
    request_id: str,
    user_id: str,
    access_groups: list[str],
    tool_name: str,
    decision: str,
    sql_hash: str | None = None,
    violations: list[dict[str, Any]] | None = None,
    duration_ms: float | None = None,
    row_count: int | None = None,
    error_code: str | None = None,
    question: str | None = None,
    path: Path | None = None,
) -> str:
    """Convenience wrapper for tool / SQL gate decisions."""

    return emit_audit_record(
        {
            "kind": "tool",
            "request_id": request_id,
            "user_id": user_id,
            "access_groups": access_groups,
            "question": question,
            "tool_name": tool_name,
            "sql_hash": sql_hash,
            "decision": decision,
            "violations": violations or [],
            "duration_ms": duration_ms,
            "row_count": row_count,
            "error_code": error_code,
        },
        path=path,
    )
