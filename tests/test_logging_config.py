"""Tests for :mod:`vai_agent.config.logging_config`."""

from __future__ import annotations

import json
import logging

import pytest

from vai_agent.config.logging_config import JsonFormatter, configure_logging
from vai_agent.config.settings import Settings


def _make_record(extra: dict[str, object] | None = None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="vai_agent.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


def test_json_formatter_emits_valid_json_with_extras() -> None:
    formatter = JsonFormatter()
    record = _make_record(extra={"request_id": "abc-123", "user_id": 7})

    line = formatter.format(record)
    payload = json.loads(line)

    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["logger"] == "vai_agent.test"
    assert payload["request_id"] == "abc-123"
    assert payload["user_id"] == 7


def test_configure_logging_replaces_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    configure_logging(settings)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handler_count_first = len(root.handlers)
    assert handler_count_first >= 1

    configure_logging(settings)
    assert len(root.handlers) == handler_count_first
