"""Logging configuration.

Phase 1 ships a small, dependency-free logging setup based on the stdlib
``logging`` module:

* ``text`` formatter — human-readable, suitable for local development.
* ``json`` formatter — single-line JSON records, suitable for production
  log aggregators (Datadog, Loki, CloudWatch, etc.).

Structured fields commonly added later (``request_id``, ``user_id``) are
already supported: any ``extra={...}`` passed to a log call will be merged
into the JSON output. The text formatter only renders them if present.

Application logs are written to ``{log_dir}/{log_file}`` (``.log`` extension).
The file handler uses JSON Lines with rotation; the console uses ``LOG_FORMAT``.
The file handler records only ``vai_agent.*`` loggers to avoid noisy
third-party traffic (watchfiles, httpx, etc.).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from vai_agent.config.settings import Settings

_APP_LOG_MAX_BYTES = 10 * 1024 * 1024
_APP_LOG_BACKUP_COUNT = 5

_STANDARD_LOG_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter. One record per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a single JSON line."""
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


class ProjectLogFilter(logging.Filter):
    """Restrict file output to first-party ``vai_agent`` loggers."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True when the record should be written to the file handler."""
        return record.name.startswith("vai_agent")


def configure_logging(settings: Settings) -> None:
    """Configure the root logger based on ``settings``.

    Safe to call multiple times; existing handlers on the root logger are
    cleared so the new configuration fully replaces the previous one.
    """

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / settings.log_file

    console_handler = logging.StreamHandler(stream=sys.stdout)
    if settings.log_format == "json":
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ),
        )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=_APP_LOG_MAX_BYTES,
        backupCount=_APP_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(ProjectLogFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        with contextlib.suppress(Exception):
            existing.flush()
        existing.close()

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(settings.log_level)

    logging.getLogger("uvicorn.error").setLevel(settings.log_level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

