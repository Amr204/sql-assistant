"""Tests for :class:`vai_agent.tools.ExplainSchemaTool`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import ProfileLoader
from vai_agent.tools.explain_schema_tool import ExplainSchemaArgs, ExplainSchemaTool
from vai_agent.users import User

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture(scope="module")
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture()
def tool(sample_profile):
    return ExplainSchemaTool(sample_profile)


@pytest.fixture()
def user():
    return User(id="u")


class TestSummary:
    def test_no_table_lists_all(self, tool, user):
        result = tool.execute(ExplainSchemaArgs(), user)
        assert result.success
        names = [t["name"] for t in result.data["tables"]]
        assert names == ["Customers", "Orders", "Order Details"]

    def test_summary_shape(self, tool, user):
        result = tool.execute(ExplainSchemaArgs(), user)
        first = result.data["tables"][0]
        assert set(first) == {
            "name", "schema", "description",
            "column_count", "primary_key", "foreign_key_count",
        }


class TestDetail:
    def test_known_table(self, tool, user):
        result = tool.execute(ExplainSchemaArgs(table="Customers"), user)
        assert result.success
        assert result.data["name"] == "Customers"
        assert result.data["primary_key"] == ["CustomerID"]
        assert result.data["columns"]
        assert all("name" in c and "type" in c for c in result.data["columns"])

    def test_table_with_space_in_name(self, tool, user):
        result = tool.execute(ExplainSchemaArgs(table="Order Details"), user)
        assert result.success
        assert result.data["name"] == "Order Details"
        assert result.data["primary_key"] == ["OrderID", "ProductID"]
        # The sample fixture has a per-table profile for "Order Details"
        assert result.data["business_name_ar"] == "تفاصيل الطلب"

    def test_unknown_table(self, tool, user):
        result = tool.execute(ExplainSchemaArgs(table="ghost"), user)
        assert not result.success
        assert "ghost" in result.error

    def test_per_table_metadata_merged(self, tool, user):
        # Customers has a per-table profile in the fixture
        result = tool.execute(ExplainSchemaArgs(table="Customers"), user)
        assert result.data["business_name_ar"] == "العملاء"
        assert "Top customers by order volume" in result.data["common_questions"]
