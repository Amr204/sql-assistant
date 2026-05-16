"""Unit tests for :mod:`vai_agent.knowledge.profile_models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vai_agent.knowledge.profile_models import (
    Cardinality,
    Column,
    Confidence,
    DatabaseSchema,
    Example,
    ForeignKeyDef,
    LanguageSettings,
    ProfileMeta,
    Relationship,
    RelationshipKind,
    SecurityPolicy,
    Table,
)


class TestProfileMeta:
    def test_minimal_input_loads(self) -> None:
        meta = ProfileMeta(profile_id="x", database_name="DB")
        assert meta.dialect == "tsql"
        assert meta.default_schema == "dbo"
        assert meta.default_row_limit == 100
        assert meta.hard_row_limit == 10_000
        assert isinstance(meta.language_settings, LanguageSettings)

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProfileMeta(profile_id="x", database_name="DB", oops="surprise")  # type: ignore[call-arg]

    def test_hard_limit_must_not_be_lower_than_default(self) -> None:
        with pytest.raises(ValidationError):
            ProfileMeta(
                profile_id="x",
                database_name="DB",
                default_row_limit=500,
                hard_row_limit=100,
            )


class TestTable:
    def test_schema_alias_accepted(self) -> None:
        t = Table.model_validate({
            "name": "Customers",
            "schema": "dbo",
            "columns": [{"name": "Id", "type": "INT", "nullable": False}],
            "primary_key": ["Id"],
        })
        assert t.schema_name == "dbo"
        assert t.name == "Customers"
        assert t.primary_key == ["Id"]

    def test_pk_column_must_exist(self) -> None:
        with pytest.raises(ValidationError):
            Table(
                name="Customers",
                columns=[Column(name="Id", type="INT", nullable=False)],
                primary_key=["MissingCol"],
            )


class TestForeignKeyDef:
    def test_balanced_columns_ok(self) -> None:
        fk = ForeignKeyDef(
            columns=["A"],
            references_table="Other",
            references_columns=["A"],
        )
        assert fk.columns == ["A"]

    def test_unbalanced_columns_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForeignKeyDef(
                columns=["A", "B"],
                references_table="Other",
                references_columns=["A"],
            )


class TestRelationship:
    def test_defaults(self) -> None:
        rel = Relationship(
            id="r1",
            from_table="A",
            from_columns=["x"],
            to_table="B",
            to_columns=["y"],
        )
        assert rel.kind is RelationshipKind.foreign_key
        assert rel.cardinality is Cardinality.many_to_one
        assert rel.confidence is Confidence.high

    def test_unbalanced_columns_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Relationship(
                id="r1",
                from_table="A",
                from_columns=["x"],
                to_table="B",
                to_columns=["y", "z"],
            )


class TestExample:
    def test_requires_at_least_one_question(self) -> None:
        with pytest.raises(ValidationError):
            Example(id="ex1", sql="SELECT 1")

    def test_arabic_only_question_is_ok(self) -> None:
        ex = Example(id="ex1", question_ar="مرحبا", sql="SELECT 1")
        assert ex.question_ar == "مرحبا"


class TestSecurityPolicy:
    def test_defaults_are_restrictive(self) -> None:
        sp = SecurityPolicy()
        assert sp.allowed_operations == ["SELECT"]
        assert "INSERT" in sp.blocked_operations
        assert "sys" in sp.blocked_schemas

    def test_operations_are_normalised_to_upper(self) -> None:
        sp = SecurityPolicy(allowed_operations=["select"], blocked_operations=["delete"])
        assert sp.allowed_operations == ["SELECT"]
        assert sp.blocked_operations == ["DELETE"]

    def test_overlapping_operations_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SecurityPolicy(
                allowed_operations=["SELECT", "DELETE"],
                blocked_operations=["DELETE"],
            )


class TestDatabaseSchema:
    def test_helper_methods(self) -> None:
        ds = DatabaseSchema(
            tables=[
                Table(name="A", columns=[Column(name="x", type="INT")]),
            ],
        )
        assert ds.has_table("A")
        assert not ds.has_table("B")
        assert ds.has_column("A", "x")
        assert not ds.has_column("A", "y")
        assert ds.table("A") is not None
        assert ds.table("B") is None
