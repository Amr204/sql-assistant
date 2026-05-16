"""Tests for the ``generate_profile_from_schema`` CLI."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from vai_agent.cli.generate_profile import main
from vai_agent.knowledge import ProfileLoader, validate_profile

MINIMAL_DDL = Path(__file__).parent / "fixtures" / "ddl" / "minimal.sql"
REAL_SCHEMA = Path(__file__).parent.parent / "data" / "input" / "Schema.sql"


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class TestHappyPath:
    def test_minimal_ddl_produces_loadable_profile(self, tmp_path: Path) -> None:
        code, out, err = _run([
            "--input", str(MINIMAL_DDL),
            "--profile", "minimal",
            "--profiles-root", str(tmp_path),
            "--database-name", "MinDB",
        ])
        assert code == 0, err
        assert "tables:         3" in out
        assert "relationships:  2" in out

        # The output must be loadable and validate cleanly.
        loader = ProfileLoader(tmp_path)
        profile = loader.load("minimal")
        assert profile.meta.database_name == "MinDB"
        assert validate_profile(profile).ok

    def test_default_database_name_is_profile_id(self, tmp_path: Path) -> None:
        code, _out, err = _run([
            "--input", str(MINIMAL_DDL),
            "--profile", "abc",
            "--profiles-root", str(tmp_path),
        ])
        assert code == 0, err
        profile = ProfileLoader(tmp_path).load("abc")
        assert profile.meta.database_name == "abc"


class TestErrorPaths:
    def test_missing_input_returns_two(self, tmp_path: Path) -> None:
        code, _out, err = _run([
            "--input", str(tmp_path / "nonexistent.sql"),
            "--profile", "x",
            "--profiles-root", str(tmp_path),
        ])
        assert code == 2
        assert "not found" in err

    def test_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        argv = [
            "--input", str(MINIMAL_DDL),
            "--profile", "minimal",
            "--profiles-root", str(tmp_path),
        ]
        code1, *_ = _run(argv)
        assert code1 == 0

        code2, _out, err = _run(argv)
        assert code2 == 1
        assert "refusing to overwrite" in err

    def test_force_overwrites(self, tmp_path: Path) -> None:
        argv = [
            "--input", str(MINIMAL_DDL),
            "--profile", "minimal",
            "--profiles-root", str(tmp_path),
        ]
        assert _run(argv)[0] == 0
        assert _run([*argv, "--force"])[0] == 0


@pytest.mark.skipif(not REAL_SCHEMA.is_file(), reason="real Schema.sql not present")
class TestRealSchema:
    def test_generates_dbnwind_profile(self, tmp_path: Path) -> None:
        code, out, err = _run([
            "--input", str(REAL_SCHEMA),
            "--profile", "dbnwind",
            "--profiles-root", str(tmp_path),
            "--database-name", "DBnwind",
        ])
        assert code == 0, err
        assert "tables:         13" in out
        assert "relationships:  13" in out

        loader = ProfileLoader(tmp_path)
        profile = loader.load("dbnwind")
        assert validate_profile(profile).ok
        assert profile.database_schema.has_table("Order Details")
