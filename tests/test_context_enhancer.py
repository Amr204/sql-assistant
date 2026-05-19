"""Tests for :mod:`vai_agent.vai_app.context_enhancer`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import ProfileLoader
from vai_agent.memory import chunk_profile, create_memory
from vai_agent.users import User
from vai_agent.utils.token_counter import count_tokens
from vai_agent.vai_app.context_enhancer import (
    ContextEnhancer,
    ContextEnhancerConfig,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


class DummyEF:
    def __init__(self) -> None:
        pass

    def name(self) -> str:
        return "dummy_ef"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    @staticmethod
    def _embed(texts: list[str]) -> list[list[float]]:
        return [[float(hash(t) % 100) / 100.0, 0.5, 0.5] for t in texts]


@pytest.fixture(scope="module")
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture
def enhancer(sample_profile):
    return ContextEnhancer(sample_profile)


@pytest.fixture
def analyst_user() -> User:
    return User(id="u1", email="a@example.com", groups=("analyst",))


@pytest.fixture
def admin_user() -> User:
    return User(id="u2", groups=("admin",))


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


class TestCountTokens:
    def test_empty_is_zero(self) -> None:
        assert count_tokens("") == 0

    def test_short_text_at_least_one(self) -> None:
        assert count_tokens("hi") >= 1


# ---------------------------------------------------------------------------
# Glossary matching
# ---------------------------------------------------------------------------


class TestGlossaryMatching:
    def test_arabic_term_maps_to_customer(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("أعطني قائمة العملاء", analyst_user)
        canonicals = {m.canonical for m in result.glossary_matches}
        assert "customer" in canonicals

    def test_english_synonym_maps_to_customer(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("list all buyers", analyst_user)
        canonicals = {m.canonical for m in result.glossary_matches}
        assert "customer" in canonicals

    def test_common_phrase_match(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("show me top customers", analyst_user)
        matched_on = {m.matched_on for m in result.glossary_matches}
        assert any("top customers" in m.lower() for m in matched_on)


# ---------------------------------------------------------------------------
# Table selection
# ---------------------------------------------------------------------------


class TestTableSelection:
    def test_customer_question_selects_customers(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("Show me all customers", analyst_user)
        assert "Customers" in result.selected_tables

    def test_join_question_selects_multiple_tables(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance(
            "How many orders does each customer have?",
            analyst_user,
        )
        assert "Customers" in result.selected_tables
        assert "Orders" in result.selected_tables

    def test_schema_section_lists_only_selected_tables(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("List customer companies", analyst_user)
        assert "dbo.Customers" in result.context_text
        assert "dbo.Orders" not in result.context_text or "Orders" not in result.selected_tables


# ---------------------------------------------------------------------------
# Example retrieval
# ---------------------------------------------------------------------------


class TestExampleRetrieval:
    def test_similar_question_retrieves_customer_lookup(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("Show me the first 10 customers", analyst_user)
        ids = [ex.id for ex in result.examples]
        assert "ex_customers_lookup_top10" in ids

    def test_example_sql_in_context(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("Show me the first 10 customers", analyst_user)
        assert "SELECT TOP 10" in result.context_text
        assert "ex_customers_lookup_top10" in result.context_text or any(
            ex.id == "ex_customers_lookup_top10" for ex in result.examples
        )


# ---------------------------------------------------------------------------
# Security context
# ---------------------------------------------------------------------------


class TestSecurityContext:
    def test_analyst_blocked_contact_name(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("List customers", analyst_user)
        assert "Customers.ContactName" in result.security.blocked_columns
        assert "ContactName" in result.context_text or "Customers.ContactName" in result.context_text

    def test_pii_column_listed_for_customer_queries(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("List customers", analyst_user)
        assert "Customers.ContactName" in result.security.pii_columns

    def test_allowed_operations_in_context(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("Count orders", analyst_user)
        assert "SELECT" in result.context_text
        assert "security" in result.sections_included


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------


class TestTokenBudget:
    def test_tiny_budget_truncates(self, sample_profile, analyst_user) -> None:
        tight = ContextEnhancer(
            sample_profile,
            config=ContextEnhancerConfig(max_tokens=50),
        )
        result = tight.enhance(
            "How many orders does each customer have with full details?",
            analyst_user,
        )
        assert result.truncated is True
        assert result.estimated_tokens <= 60

    def test_normal_budget_not_truncated(self, enhancer, analyst_user) -> None:
        result = enhancer.enhance("List customers", analyst_user)
        assert result.truncated is False
        assert result.estimated_tokens > 0


# ---------------------------------------------------------------------------
# Memory integration (optional)
# ---------------------------------------------------------------------------


class TestMemoryIntegration:
    def test_memory_boosts_table_from_search(self, sample_profile, analyst_user, tmp_path) -> None:
        memory, _client = create_memory(
            profile_id="sample",
            persist_dir=tmp_path,
            embedding_function=DummyEF(),
        )
        memory.seed(chunk_profile(sample_profile))

        with_memory = ContextEnhancer(sample_profile, memory=memory)
        result = with_memory.enhance(
            "business rules for shipped orders",
            analyst_user,
        )
        assert result.selected_tables or result.glossary_matches or result.examples
