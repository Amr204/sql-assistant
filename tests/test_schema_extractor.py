"""Unit and smoke tests for :mod:`vai_agent.db.schema_extractor`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.db.schema_extractor import (
    _balanced_paren_end,
    _split_top_level_commas,
    parse_schema_sql,
    split_go_batches,
)
from vai_agent.knowledge.profile_generator import read_schema_file

MINIMAL_DDL = Path(__file__).parent / "fixtures" / "ddl" / "minimal.sql"
REAL_SCHEMA = Path(__file__).parent.parent / "data" / "input" / "Schema.sql"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


class TestSplitGoBatches:
    def test_basic_split(self) -> None:
        text = "SELECT 1\nGO\nSELECT 2\nGO\n"
        assert split_go_batches(text) == ["SELECT 1", "SELECT 2"]

    def test_case_insensitive(self) -> None:
        assert split_go_batches("a\ngo\nb\nGO\n") == ["a", "b"]

    def test_ignores_go_inside_a_line(self) -> None:
        # 'GO' appearing inside text on a line with other content is not a
        # separator (the line is taken verbatim).
        text = "SELECT 'GO TEAM'\nGO\nSELECT 1"
        assert split_go_batches(text) == ["SELECT 'GO TEAM'", "SELECT 1"]

    def test_trailing_whitespace_around_go(self) -> None:
        assert split_go_batches("a\n  GO  \nb") == ["a", "b"]

    def test_empty_input(self) -> None:
        assert split_go_batches("") == []


class TestBalancedParens:
    def test_simple(self) -> None:
        assert _balanced_paren_end("(abc)", 0) == 4

    def test_nested(self) -> None:
        assert _balanced_paren_end("((a)(b))", 0) == 7

    def test_ignores_quoted_parens(self) -> None:
        assert _balanced_paren_end("('(' || 'x')", 0) == 11

    def test_unbalanced_raises(self) -> None:
        with pytest.raises(ValueError):
            _balanced_paren_end("(abc", 0)


class TestTopLevelCommaSplit:
    def test_flat(self) -> None:
        assert _split_top_level_commas("a, b, c") == ["a", " b", " c"]

    def test_respects_parens(self) -> None:
        assert _split_top_level_commas("a, foo(b, c), d") == ["a", " foo(b, c)", " d"]


# ---------------------------------------------------------------------------
# CREATE TABLE parsing
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def parsed_minimal():
    return parse_schema_sql(MINIMAL_DDL.read_text(encoding="utf-8"))


class TestParseCreateTable:
    def test_all_tables_found(self, parsed_minimal) -> None:
        names = [t.name for t in parsed_minimal.database_schema.tables]
        assert names == ["Customers", "Orders", "Order Details"]

    def test_table_name_with_space_is_preserved(self, parsed_minimal) -> None:
        od = parsed_minimal.database_schema.table("Order Details")
        assert od is not None
        assert od.name == "Order Details"

    def test_columns_with_sizes(self, parsed_minimal) -> None:
        customers = parsed_minimal.database_schema.table("Customers")
        assert customers is not None
        types = {c.name: c.type for c in customers.columns}
        assert types["CustomerID"] == "nchar(5)"
        assert types["CompanyName"] == "nvarchar(40)"
        assert types["ContactName"] == "nvarchar(30)"

    def test_nullability(self, parsed_minimal) -> None:
        customers = parsed_minimal.database_schema.table("Customers")
        nullability = {c.name: c.nullable for c in customers.columns}
        assert nullability == {
            "CustomerID": False,
            "CompanyName": False,
            "ContactName": True,
        }

    def test_identity_columns(self, parsed_minimal) -> None:
        orders = parsed_minimal.database_schema.table("Orders")
        assert orders is not None
        order_id = next(c for c in orders.columns if c.name == "OrderID")
        assert "IDENTITY(1,1)" in order_id.type

    def test_simple_primary_key(self, parsed_minimal) -> None:
        orders = parsed_minimal.database_schema.table("Orders")
        assert orders.primary_key == ["OrderID"]

    def test_composite_primary_key(self, parsed_minimal) -> None:
        od = parsed_minimal.database_schema.table("Order Details")
        assert od.primary_key == ["OrderID", "ProductID"]


# ---------------------------------------------------------------------------
# Foreign keys, defaults, indexes
# ---------------------------------------------------------------------------


class TestForeignKeys:
    def test_fks_attached_to_source_table(self, parsed_minimal) -> None:
        orders = parsed_minimal.database_schema.table("Orders")
        fk_names = [fk.name for fk in orders.foreign_keys]
        assert fk_names == ["FK_Orders_Customers"]
        fk = orders.foreign_keys[0]
        assert fk.columns == ["CustomerID"]
        assert fk.references_table == "Customers"
        assert fk.references_columns == ["CustomerID"]

    def test_fk_on_space_table(self, parsed_minimal) -> None:
        od = parsed_minimal.database_schema.table("Order Details")
        fk_names = [fk.name for fk in od.foreign_keys]
        assert "FK_Order_Details_Orders" in fk_names

    def test_relationships_derived_from_fks(self, parsed_minimal) -> None:
        rel_ids = {r.id for r in parsed_minimal.relationships}
        assert "rel_orders_customers" in rel_ids
        assert "rel_order_details_orders" in rel_ids

    def test_relationship_reason_mentions_constraint(self, parsed_minimal) -> None:
        rel = next(
            r for r in parsed_minimal.relationships
            if r.id == "rel_orders_customers"
        )
        assert rel.reason and "FK_Orders_Customers" in rel.reason


class TestDefaults:
    def test_defaults_applied_to_columns(self, parsed_minimal) -> None:
        orders = parsed_minimal.database_schema.table("Orders")
        freight = next(c for c in orders.columns if c.name == "Freight")
        assert freight.default == "((0))"

    def test_default_on_space_table(self, parsed_minimal) -> None:
        od = parsed_minimal.database_schema.table("Order Details")
        qty = next(c for c in od.columns if c.name == "Quantity")
        assert qty.default == "((1))"


class TestIndexes:
    def test_non_unique_index_attached(self, parsed_minimal) -> None:
        orders = parsed_minimal.database_schema.table("Orders")
        ix = next(i for i in orders.indexes if i.name == "IX_Orders_CustomerID")
        assert ix.columns == ["CustomerID"]
        assert ix.unique is False

    def test_unique_index_flagged(self, parsed_minimal) -> None:
        customers = parsed_minimal.database_schema.table("Customers")
        ix = next(i for i in customers.indexes if i.name == "UX_Customers_CompanyName")
        assert ix.unique is True


# ---------------------------------------------------------------------------
# Views and procedures
# ---------------------------------------------------------------------------


class TestViewsAndProcedures:
    def test_view_with_space_in_name(self, parsed_minimal) -> None:
        names = [v.name for v in parsed_minimal.database_schema.views]
        assert "Active Customers" in names

    def test_view_body_captured(self, parsed_minimal) -> None:
        view = next(
            v for v in parsed_minimal.database_schema.views
            if v.name == "Active Customers"
        )
        assert view.definition is not None
        assert "SELECT" in view.definition

    def test_procedure_captured(self, parsed_minimal) -> None:
        procs = parsed_minimal.database_schema.stored_procedures
        names = [p.name for p in procs]
        assert "GetCustomerOrders" in names

    def test_procedure_definition_includes_param(self, parsed_minimal) -> None:
        proc = next(
            p for p in parsed_minimal.database_schema.stored_procedures
            if p.name == "GetCustomerOrders"
        )
        assert proc.definition is not None
        assert "@CustomerID" in proc.definition


# ---------------------------------------------------------------------------
# Smoke test against the real DBnwind schema
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_SCHEMA.is_file(), reason="real Schema.sql not present")
class TestRealNorthwindSchema:
    @pytest.fixture(scope="class")
    def parsed_real(self):
        return parse_schema_sql(read_schema_file(REAL_SCHEMA))

    def test_table_count(self, parsed_real) -> None:
        assert len(parsed_real.database_schema.tables) == 13

    def test_specific_tables_present(self, parsed_real) -> None:
        names = {t.name for t in parsed_real.database_schema.tables}
        assert {"Customers", "Orders", "Order Details", "Products", "Employees"} <= names

    def test_self_referential_fk_on_employees(self, parsed_real) -> None:
        rel_ids = {r.id for r in parsed_real.relationships}
        assert "rel_employees_employees" in rel_ids

    def test_view_with_spaces_captured(self, parsed_real) -> None:
        view_names = {v.name for v in parsed_real.database_schema.views}
        assert "Customer and Suppliers by City" in view_names
        assert "Order Details Extended" in view_names

    def test_thirteen_relationships(self, parsed_real) -> None:
        assert len(parsed_real.relationships) == 13

    def test_order_details_composite_pk(self, parsed_real) -> None:
        od = parsed_real.database_schema.table("Order Details")
        assert od is not None
        assert od.primary_key == ["OrderID", "ProductID"]

    def test_order_details_has_two_fks(self, parsed_real) -> None:
        od = parsed_real.database_schema.table("Order Details")
        fk_targets = {fk.references_table for fk in od.foreign_keys}
        assert fk_targets == {"Orders", "Products"}

    def test_order_details_has_four_indexes(self, parsed_real) -> None:
        od = parsed_real.database_schema.table("Order Details")
        assert len(od.indexes) == 4

    def test_seven_stored_procedures(self, parsed_real) -> None:
        assert len(parsed_real.database_schema.stored_procedures) == 7
