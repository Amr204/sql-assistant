"""Tests for :class:`vai_agent.knowledge.ProfileLoader`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import (
    Profile,
    ProfileFileError,
    ProfileLoader,
    ProfileNotFoundError,
)

FIXTURE_PROFILES_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture()
def loader() -> ProfileLoader:
    return ProfileLoader(FIXTURE_PROFILES_ROOT)


class TestLoadSampleProfile:
    def test_returns_profile_instance(self, loader: ProfileLoader) -> None:
        profile = loader.load("sample")
        assert isinstance(profile, Profile)
        assert profile.meta.profile_id == "sample"
        assert profile.meta.database_name == "NorthwindSample"

    def test_schema_is_populated(self, loader: ProfileLoader) -> None:
        profile = loader.load("sample")
        names = [t.name for t in profile.database_schema.tables]
        assert names == ["Customers", "Orders", "Order Details"]
        orders = profile.database_schema.table("Orders")
        assert orders is not None
        assert orders.primary_key == ["OrderID"]
        assert len(orders.foreign_keys) == 1

    def test_relationships_loaded(self, loader: ProfileLoader) -> None:
        profile = loader.load("sample")
        ids = [r.id for r in profile.relationships.relationships]
        assert ids == ["rel_orders_customers", "rel_order_details_orders"]

    def test_examples_loaded(self, loader: ProfileLoader) -> None:
        profile = loader.load("sample")
        assert len(profile.examples.examples) >= 2
        first = profile.examples.examples[0]
        assert first.question_ar and first.question_en
        assert first.id.startswith("ex_")

    def test_per_table_profiles_loaded(self, loader: ProfileLoader) -> None:
        profile = loader.load("sample")
        assert set(profile.tables) == {"Customers", "Orders", "Order Details"}
        assert profile.tables["Customers"].business_name_ar == "العملاء"

    def test_table_names_with_spaces_are_preserved_end_to_end(
        self, loader: ProfileLoader,
    ) -> None:
        """Regression: real Northwind has 'Order Details' (with a space).

        Verify that a space in a table name survives the full pipeline —
        schema parsing, relationships, per-table profile lookup, and the
        ``DatabaseSchema`` helper methods.
        """
        profile = loader.load("sample")
        schema = profile.database_schema

        assert schema.has_table("Order Details")
        assert not schema.has_table("OrderDetails")
        assert schema.has_column("Order Details", "OrderID")

        rel = next(
            r for r in profile.relationships.relationships
            if r.from_table == "Order Details"
        )
        assert rel.from_columns == ["OrderID"]
        assert rel.to_table == "Orders"

        tp = profile.tables["Order Details"]
        assert tp.name == "Order Details"
        assert tp.primary_key == ["OrderID", "ProductID"]

    def test_security_policy_loaded(self, loader: ProfileLoader) -> None:
        profile = loader.load("sample")
        sp = profile.security_policy
        assert sp.allowed_operations == ["SELECT"]
        assert "Customers.ContactName" in sp.pii_columns


class TestErrorHandling:
    def test_missing_profile_dir_raises(self, loader: ProfileLoader) -> None:
        with pytest.raises(ProfileNotFoundError):
            loader.load("does-not-exist")

    def test_missing_mandatory_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "broken").mkdir()
        # Only profile.yaml, no schema.generated.yaml
        (tmp_path / "broken" / "profile.yaml").write_text(
            "profile_id: broken\ndatabase_name: x\n", encoding="utf-8",
        )
        loader = ProfileLoader(tmp_path)
        with pytest.raises(ProfileFileError, match=r"schema\.generated\.yaml"):
            loader.load("broken")

    def test_optional_files_default_to_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "minimal"
        d.mkdir()
        (d / "profile.yaml").write_text(
            "profile_id: minimal\ndatabase_name: x\n", encoding="utf-8",
        )
        (d / "schema.generated.yaml").write_text("tables: []\n", encoding="utf-8")

        profile = ProfileLoader(tmp_path).load("minimal")
        assert profile.relationships.relationships == []
        assert profile.examples.examples == []
        assert profile.metrics.metrics == []
        assert profile.glossary.terms == []
        assert profile.tables == {}
        assert profile.security_policy.allowed_operations == ["SELECT"]

    def test_malformed_yaml_raises_profile_file_error(self, tmp_path: Path) -> None:
        d = tmp_path / "bad-yaml"
        d.mkdir()
        (d / "profile.yaml").write_text("profile_id: x\n  bad: : :\n", encoding="utf-8")
        (d / "schema.generated.yaml").write_text("tables: []\n", encoding="utf-8")
        with pytest.raises(ProfileFileError, match="invalid YAML"):
            ProfileLoader(tmp_path).load("bad-yaml")

    def test_typo_in_field_is_caught_by_pydantic(self, tmp_path: Path) -> None:
        d = tmp_path / "typo"
        d.mkdir()
        (d / "profile.yaml").write_text(
            "profile_id: t\ndatabase_name: x\ndatabse_type: mssql\n",
            encoding="utf-8",
        )
        (d / "schema.generated.yaml").write_text("tables: []\n", encoding="utf-8")
        with pytest.raises(ProfileFileError):
            ProfileLoader(tmp_path).load("typo")

    def test_duplicate_table_profile_rejected(self, tmp_path: Path) -> None:
        d = tmp_path / "dup"
        (d / "tables").mkdir(parents=True)
        (d / "profile.yaml").write_text(
            "profile_id: d\ndatabase_name: x\n", encoding="utf-8",
        )
        (d / "schema.generated.yaml").write_text("tables: []\n", encoding="utf-8")
        (d / "tables" / "a.yaml").write_text("name: Customers\n", encoding="utf-8")
        (d / "tables" / "b.yaml").write_text("name: Customers\n", encoding="utf-8")
        with pytest.raises(ProfileFileError, match="duplicate table profile"):
            ProfileLoader(tmp_path).load("dup")
