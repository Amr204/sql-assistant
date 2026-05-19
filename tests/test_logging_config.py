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


def test_configure_logging_replaces_handlers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    log_root = tmp_path / "logs"
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        log_dir=str(log_root),
        log_file="app.log",
    )

    configure_logging(settings)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 2

    configure_logging(settings)
    assert len(root.handlers) == 2


def test_file_handler_writes_json_lines(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "text")
    log_dir = tmp_path / "logs"
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        log_dir=str(log_dir),
        log_file="app.log",
        log_format="text",
    )

    configure_logging(settings)

    assert log_dir.is_dir()
    log_path = log_dir / "app.log"
    assert log_path.is_file()

    log = logging.getLogger("vai_agent.test_file_json")
    log.info("hello", extra={"request_id": "abc"})
    for h in logging.getLogger().handlers:
        h.flush()

    line = log_path.read_text(encoding="utf-8").strip().splitlines()[0]
    payload = json.loads(line)

    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["logger"] == "vai_agent.test_file_json"
    assert payload["request_id"] == "abc"


def test_file_handler_only_records_vai_agent_loggers(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "text")
    log_dir = tmp_path / "logs"
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        log_dir=str(log_dir),
        log_file="app.log",
        log_format="text",
    )
    configure_logging(settings)
    log_path = log_dir / "app.log"

    logging.getLogger("watchfiles.main").info("watchfiles-noise")
    logging.getLogger("vai_agent.file_only_test").info("keep-this")
    for h in logging.getLogger().handlers:
        h.flush()

    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["logger"] == "vai_agent.file_only_test"
    assert "watchfiles-noise" not in log_path.read_text()
