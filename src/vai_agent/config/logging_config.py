"""Logging configuration.

Phase 1 ships a small, dependency-free logging setup based on the stdlib
``logging`` module:

* ``text`` formatter — human-readable, suitable for local development.
* ``json`` formatter — single-line JSON records, suitable for production
  log aggregators (Datadog, Loki, CloudWatch, etc.).

Structured fields commonly added later (``request_id``, ``user_id``) are
already supported: any ``extra={...}`` passed to a log call will be merged
into the JSON output. The text formatter only renders them if present.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from typing import Any

from vai_agent.config.settings import Settings

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


def configure_logging(settings: Settings) -> None:
    """Configure the root logger based on ``settings``.

    Safe to call multiple times; existing handlers on the root logger are
    cleared so the new configuration fully replaces the previous one.
    """

    handler = logging.StreamHandler(stream=sys.stdout)

    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    logging.getLogger("uvicorn.error").setLevel(settings.log_level)
    logging.getLogger("uvicorn.access").setLevel(settings.log_level)
