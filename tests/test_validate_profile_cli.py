"""Tests for the ``validate_profile`` CLI."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from vai_agent.cli.validate_profile import main

FIXTURE_PROFILES_ROOT = Path(__file__).parent / "fixtures" / "profiles"


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class TestValidateProfileCli:
    def test_valid_profile_returns_zero(self) -> None:
        code, out, err = _run([
            "--profile", "sample",
            "--profiles-root", str(FIXTURE_PROFILES_ROOT),
        ])
        assert code == 0, err
        assert "profile: sample" in out
        assert "errors:   0" in out

    def test_missing_profile_returns_two(self) -> None:
        code, _out, err = _run([
            "--profile", "ghost",
            "--profiles-root", str(FIXTURE_PROFILES_ROOT),
        ])
        assert code == 2
        assert "ghost" in err

    def test_invalid_profile_returns_one(self, tmp_path: Path) -> None:
        """Build a broken profile on the fly and confirm the CLI exits 1."""

        d = tmp_path / "broken"
        d.mkdir()
        (d / "profile.yaml").write_text(
            "profile_id: broken\ndatabase_name: x\n", encoding="utf-8",
        )
        (d / "schema.generated.yaml").write_text("tables: []\n", encoding="utf-8")
        (d / "relationships.yaml").write_text(
            "relationships:\n"
            "  - id: r1\n"
            "    from_table: Ghost\n"
            "    from_columns: [x]\n"
            "    to_table: AlsoGhost\n"
            "    to_columns: [y]\n",
            encoding="utf-8",
        )

        code, out, _err = _run([
            "--profile", "broken",
            "--profiles-root", str(tmp_path),
        ])
        assert code == 1
        assert "REL001" in out or "REL003" in out

    def test_strict_promotes_warnings(self, tmp_path: Path) -> None:
        d = tmp_path / "warns"
        d.mkdir()
        (d / "profile.yaml").write_text(
            "profile_id: warns\ndatabase_name: x\n", encoding="utf-8",
        )
        (d / "schema.generated.yaml").write_text("tables: []\n", encoding="utf-8")
        (d / "examples.yaml").write_text(
            "examples:\n"
            "  - id: ex\n"
            "    question_en: q\n"
            "    sql: SELECT 1\n"
            "    required_tables: [Missing]\n",
            encoding="utf-8",
        )

        code_normal, *_ = _run([
            "--profile", "warns",
            "--profiles-root", str(tmp_path),
        ])
        code_strict, *_ = _run([
            "--profile", "warns",
            "--profiles-root", str(tmp_path),
            "--strict",
        ])

        assert code_normal == 0
        assert code_strict == 1

    def test_missing_profile_argument_exits_two(self) -> None:
        with pytest.raises(SystemExit):
            main([])
