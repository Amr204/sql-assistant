"""Activity audit JSONL log."""

from __future__ import annotations

import json
from pathlib import Path

from vai_agent.audit.activity_recorder import ActivityEvent, ActivityRecorder


def test_activity_recorder_appends_jsonl_row(tmp_path: Path) -> None:
    rec = ActivityRecorder(str(tmp_path), "activity_log.xlsx")
    rec.record(
        ActivityEvent(
            request_id="r1",
            event_type="request.received",
            status="received",
            question="SELECT 1",
            user_id="u1",
        ),
    )
    path = tmp_path / "activity_log.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["request_id"] == "r1"
    assert row["event_type"] == "request.received"
    assert row["question"] == "SELECT 1"


def test_activity_event_does_not_embed_connection_secrets() -> None:
    ev = ActivityEvent(
        request_id="x",
        event_type="sql.execute",
        status="error",
        generated_sql="SELECT 1",
        executed_sql="SELECT 1",
        error_message="login failed for user 'x'",
    )
    assert "PWD=" not in str(ev)
    assert "OPENROUTER" not in str(ev)


def test_safe_record_activity_swallows_recorder_errors() -> None:
    from unittest.mock import MagicMock

    from vai_agent.audit.activity_recorder import safe_record_activity

    bad = MagicMock()
    bad.record.side_effect = OSError("locked")
    safe_record_activity(
        bad,
        ActivityEvent(request_id="r", event_type="request.received", status="ok"),
    )
