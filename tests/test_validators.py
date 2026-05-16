"""Tests for :mod:`vai_agent.knowledge.validators`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import (
    Profile,
    ProfileLoader,
    Severity,
    validate_profile,
)
from vai_agent.knowledge.profile_models import (
    Column,
    DatabaseSchema,
    Example,
    ExamplesDocument,
    ProfileMeta,
    Relationship,
    RelationshipsDocument,
    SecurityPolicy,
    Table,
    TableProfile,
)

FIXTURE_PROFILES_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture()
def sample_profile() -> Profile:
    return ProfileLoader(FIXTURE_PROFILES_ROOT).load("sample")


def _profile_with(**overrides: object) -> Profile:
    """Build a minimal profile for targeted validation tests."""

    base = {
        "meta": ProfileMeta(profile_id="t", database_name="db"),
        "database_schema": DatabaseSchema(
            tables=[
                Table(
                    name="Customers",
                    columns=[
                        Column(name="CustomerID", type="INT", nullable=False),
                        Column(name="Name", type="NVARCHAR(50)"),
                    ],
                    primary_key=["CustomerID"],
                ),
                Table(
                    name="Orders",
                    columns=[
                        Column(name="OrderID", type="INT", nullable=False),
                        Column(name="CustomerID", type="INT"),
                    ],
                    primary_key=["OrderID"],
                ),
            ],
        ),
    }
    base.update(overrides)  # type: ignore[arg-type]
    return Profile(**base)  # type: ignore[arg-type]


class TestSampleProfileHasNoErrors:
    def test_sample_profile_is_clean(self, sample_profile: Profile) -> None:
        report = validate_profile(sample_profile)
        assert report.profile_id == "sample"
        assert report.ok, f"unexpected errors: {report.errors}"


class TestRelationshipChecks:
    def test_missing_from_table_is_error(self) -> None:
        profile = _profile_with(
            relationships=RelationshipsDocument(
                relationships=[
                    Relationship(
                        id="r",
                        from_table="Ghost",
                        from_columns=["x"],
                        to_table="Customers",
                        to_columns=["CustomerID"],
                    ),
                ],
            ),
        )
        report = validate_profile(profile)
        codes = {i.code for i in report.errors}
        assert "REL001" in codes
        assert not report.ok

    def test_missing_to_column_is_error(self) -> None:
        profile = _profile_with(
            relationships=RelationshipsDocument(
                relationships=[
                    Relationship(
                        id="r",
                        from_table="Orders",
                        from_columns=["CustomerID"],
                        to_table="Customers",
                        to_columns=["GhostCol"],
                    ),
                ],
            ),
        )
        report = validate_profile(profile)
        assert "REL004" in {i.code for i in report.errors}


class TestExampleChecks:
    def test_forbidden_first_keyword_is_error(self) -> None:
        profile = _profile_with(
            examples=ExamplesDocument(
                examples=[
                    Example(
                        id="bad",
                        question_en="delete things",
                        sql="DELETE FROM Customers WHERE 1=1",
                    ),
                ],
            ),
        )
        report = validate_profile(profile)
        codes = {i.code for i in report.errors}
        assert "EX002" in codes

    def test_duplicate_example_id_is_error(self) -> None:
        profile = _profile_with(
            examples=ExamplesDocument(
                examples=[
                    Example(id="dup", question_en="a", sql="SELECT 1"),
                    Example(id="dup", question_en="b", sql="SELECT 2"),
                ],
            ),
        )
        report = validate_profile(profile)
        assert "EX001" in {i.code for i in report.errors}

    def test_unknown_required_table_is_warning(self) -> None:
        profile = _profile_with(
            examples=ExamplesDocument(
                examples=[
                    Example(
                        id="ex",
                        question_en="q",
                        sql="SELECT TOP 1 1",
                        required_tables=["MissingTable"],
                    ),
                ],
            ),
        )
        report = validate_profile(profile)
        assert "EX004" in {i.code for i in report.warnings}
        assert report.ok  # warnings don't fail validation

    def test_with_cte_is_recognised_as_select(self) -> None:
        profile = _profile_with(
            examples=ExamplesDocument(
                examples=[
                    Example(
                        id="cte",
                        question_en="cte query",
                        sql="WITH c AS (SELECT 1 AS x) SELECT * FROM c",
                    ),
                ],
            ),
        )
        report = validate_profile(profile)
        # No error and no EX003 warning
        assert "EX003" not in {i.code for i in report.issues}
        assert "EX002" not in {i.code for i in report.issues}


class TestSecurityPolicyChecks:
    def test_overlapping_schemas_is_error(self) -> None:
        profile = _profile_with(
            security_policy=SecurityPolicy(
                allowed_schemas=["dbo", "audit"],
                blocked_schemas=["audit"],
            ),
        )
        report = validate_profile(profile)
        assert "SEC001" in {i.code for i in report.errors}

    def test_default_limit_above_max_rows_is_error(self) -> None:
        profile = _profile_with(
            security_policy=SecurityPolicy(default_limit=5000, max_rows=1000),
        )
        report = validate_profile(profile)
        assert "SEC004" in {i.code for i in report.errors}

    def test_missing_select_is_warning(self) -> None:
        profile = _profile_with(
            security_policy=SecurityPolicy(
                allowed_operations=["EXPLAIN"],
                blocked_operations=["INSERT"],
            ),
        )
        report = validate_profile(profile)
        assert "SEC003" in {i.code for i in report.warnings}


class TestPerTableProfileChecks:
    def test_unknown_table_in_per_table_profile_is_error(self) -> None:
        profile = _profile_with(
            tables={"Ghost": TableProfile(name="Ghost", primary_key=[])},
        )
        report = validate_profile(profile)
        assert "TP002" in {i.code for i in report.errors}

    def test_unknown_pk_column_is_warning(self) -> None:
        profile = _profile_with(
            tables={
                "Customers": TableProfile(
                    name="Customers",
                    primary_key=["NoSuchCol"],
                ),
            },
        )
        report = validate_profile(profile)
        codes = {i.code for i in report.warnings}
        assert "TP003" in codes


class TestReportShape:
    def test_severity_split(self) -> None:
        profile = _profile_with(
            tables={"Ghost": TableProfile(name="Ghost")},  # produces TP002 error
            examples=ExamplesDocument(
                examples=[
                    Example(
                        id="x",
                        question_en="q",
                        sql="SELECT 1",
                        required_tables=["Missing"],  # produces EX004 warning
                    ),
                ],
            ),
        )
        report = validate_profile(profile)
        assert len(report.errors) >= 1
        assert len(report.warnings) >= 1
        assert all(i.severity is Severity.error for i in report.errors)
        assert all(i.severity is Severity.warning for i in report.warnings)
