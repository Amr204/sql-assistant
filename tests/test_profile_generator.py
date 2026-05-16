"""Tests for :mod:`vai_agent.knowledge.profile_generator`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from vai_agent.db.schema_extractor import parse_schema_sql
from vai_agent.knowledge import ProfileLoader, validate_profile
from vai_agent.knowledge.profile_generator import (
    _safe_filename,
    generate_profile,
    read_schema_file,
    write_profile_to_disk,
)

MINIMAL_DDL = Path(__file__).parent / "fixtures" / "ddl" / "minimal.sql"
REAL_SCHEMA = Path(__file__).parent.parent / "data" / "input" / "Schema.sql"

FIXED_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def extracted_minimal():
    return parse_schema_sql(MINIMAL_DDL.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------


class TestSafeFilename:
    def test_space_becomes_underscore(self) -> None:
        assert _safe_filename("Order Details") == "Order_Details"

    def test_strips_unsafe_chars(self) -> None:
        assert _safe_filename("foo/bar:baz") == "foobarbaz"

    def test_keeps_hyphen_and_alphanumeric(self) -> None:
        assert _safe_filename("My-Table_2") == "My-Table_2"

    def test_empty_falls_back(self) -> None:
        assert _safe_filename("   ") == "table"


# ---------------------------------------------------------------------------
# generate_profile()
# ---------------------------------------------------------------------------


class TestGenerateProfile:
    def test_meta_populated_from_args(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="test",
            database_name="TestDB",
            source_path=MINIMAL_DDL,
            now=FIXED_NOW,
        )
        assert profile.meta.profile_id == "test"
        assert profile.meta.database_name == "TestDB"
        assert profile.meta.created_at == FIXED_NOW
        assert profile.meta.generated_from == str(MINIMAL_DDL)

    def test_schema_carried_through(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t",
        )
        names = [t.name for t in profile.database_schema.tables]
        assert names == ["Customers", "Orders", "Order Details"]

    def test_relationships_carried_through(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t",
        )
        ids = {r.id for r in profile.relationships.relationships}
        assert ids == {"rel_orders_customers", "rel_order_details_orders"}

    def test_per_table_profiles_for_each_table(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t",
        )
        assert set(profile.tables) == {"Customers", "Orders", "Order Details"}

    def test_per_table_profile_picks_up_pk(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t",
        )
        assert profile.tables["Order Details"].primary_key == ["OrderID", "ProductID"]

    def test_date_columns_detected_by_type(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t",
        )
        assert "OrderDate" in profile.tables["Orders"].date_columns

    def test_per_table_profile_has_low_confidence(self, extracted_minimal) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t",
        )
        assert profile.tables["Orders"].confidence.value == "low"


# ---------------------------------------------------------------------------
# write_profile_to_disk()
# ---------------------------------------------------------------------------


class TestWriteProfile:
    def test_creates_expected_files(self, extracted_minimal, tmp_path: Path) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t", now=FIXED_NOW,
        )
        out = tmp_path / "test"
        written = write_profile_to_disk(profile, out)

        names = {p.name for p in written}
        assert {"profile.yaml", "schema.generated.yaml", "relationships.yaml"} <= names
        assert (out / "tables").is_dir()
        assert (out / "tables" / "Order_Details.yaml").is_file()

    def test_refuses_overwrite_without_force(
        self, extracted_minimal, tmp_path: Path,
    ) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t", now=FIXED_NOW,
        )
        out = tmp_path / "test"
        write_profile_to_disk(profile, out)

        with pytest.raises(FileExistsError):
            write_profile_to_disk(profile, out)

    def test_force_overwrites(self, extracted_minimal, tmp_path: Path) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t", now=FIXED_NOW,
        )
        out = tmp_path / "test"
        write_profile_to_disk(profile, out)
        # second run must not raise
        write_profile_to_disk(profile, out, force=True)

    def test_idempotent_byte_for_byte(
        self, extracted_minimal, tmp_path: Path,
    ) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="t", database_name="t", now=FIXED_NOW,
        )
        first = tmp_path / "first"
        second = tmp_path / "second"
        write_profile_to_disk(profile, first)
        write_profile_to_disk(profile, second)
        for filename in ("profile.yaml", "schema.generated.yaml", "relationships.yaml"):
            assert (first / filename).read_bytes() == (second / filename).read_bytes()
        for tbl in (first / "tables").iterdir():
            assert tbl.read_bytes() == (second / "tables" / tbl.name).read_bytes()


# ---------------------------------------------------------------------------
# Round-trip: extract -> generate -> write -> load -> validate
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_minimal_ddl_loads_and_validates_clean(
        self, extracted_minimal, tmp_path: Path,
    ) -> None:
        profile = generate_profile(
            extracted=extracted_minimal,
            profile_id="rt", database_name="rt", now=FIXED_NOW,
        )
        write_profile_to_disk(profile, tmp_path / "rt")

        reloaded = ProfileLoader(tmp_path).load("rt")
        report = validate_profile(reloaded)
        assert report.ok, f"unexpected errors: {report.errors}"
        # Sanity check the key invariants survived the round trip.
        assert reloaded.database_schema.has_table("Order Details")
        assert "rel_order_details_orders" in {
            r.id for r in reloaded.relationships.relationships
        }
        assert "Order Details" in reloaded.tables

    @pytest.mark.skipif(not REAL_SCHEMA.is_file(), reason="real Schema.sql not present")
    def test_real_northwind_round_trip(self, tmp_path: Path) -> None:
        text = read_schema_file(REAL_SCHEMA)
        extracted = parse_schema_sql(text)
        profile = generate_profile(
            extracted=extracted,
            profile_id="dbnwind",
            database_name="DBnwind",
            source_path=REAL_SCHEMA,
            now=FIXED_NOW,
        )
        write_profile_to_disk(profile, tmp_path / "dbnwind")

        reloaded = ProfileLoader(tmp_path).load("dbnwind")
        report = validate_profile(reloaded)
        assert report.ok, f"unexpected errors: {report.errors}"
        assert len(reloaded.database_schema.tables) == 13
        assert len(reloaded.relationships.relationships) == 13
