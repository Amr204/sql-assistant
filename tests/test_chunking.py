"""Tests for :mod:`vai_agent.memory.chunking`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.chunking import ProfileChunk, _safe_slug, chunk_profile

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture(scope="module")
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture(scope="module")
def chunks(sample_profile):
    return chunk_profile(sample_profile)


# ---------------------------------------------------------------------------
# _safe_slug helper
# ---------------------------------------------------------------------------


class TestSafeSlug:
    def test_spaces_become_underscores(self) -> None:
        assert _safe_slug("Order Details") == "order_details"

    def test_special_chars_stripped(self) -> None:
        assert _safe_slug("foo/bar:baz") == "foobarbaz"

    def test_truncated_to_max_len(self) -> None:
        long = "a" * 100
        assert len(_safe_slug(long, max_len=20)) <= 20

    def test_empty_falls_back(self) -> None:
        assert _safe_slug("   ") == "chunk"

    def test_arabic_stripped_safely(self) -> None:
        # Arabic chars are stripped (not ASCII); slug is non-empty due to fallback
        result = _safe_slug("عميل")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# chunk_profile output
# ---------------------------------------------------------------------------


class TestChunkProfile:
    def test_returns_list_of_profile_chunks(self, chunks) -> None:
        assert all(isinstance(c, ProfileChunk) for c in chunks)

    def test_ids_are_unique(self, chunks) -> None:
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_ids_prefixed_with_profile_id(self, chunks) -> None:
        assert all(c.id.startswith("sample:") for c in chunks)

    def test_all_chunks_have_non_empty_document(self, chunks) -> None:
        assert all(c.document.strip() for c in chunks)

    def test_metadata_contains_profile_id_and_kind(self, chunks) -> None:
        for c in chunks:
            assert c.metadata.get("profile_id") == "sample"
            assert c.metadata.get("kind")

    def test_deterministic_ordering(self, sample_profile) -> None:
        a = chunk_profile(sample_profile)
        b = chunk_profile(sample_profile)
        assert [c.id for c in a] == [c.id for c in b]


# ---------------------------------------------------------------------------
# Per-kind coverage
# ---------------------------------------------------------------------------


class TestChunkKinds:
    def _by_kind(self, chunks, kind: str) -> list[ProfileChunk]:
        return [c for c in chunks if c.metadata.get("kind") == kind]

    def test_schema_table_chunks_present(self, chunks) -> None:
        tables = self._by_kind(chunks, "schema_table")
        table_names = {c.metadata["table"] for c in tables}
        assert table_names == {"Customers", "Orders", "Order Details"}

    def test_schema_table_has_column_info(self, chunks) -> None:
        customers_chunk = next(
            c for c in chunks
            if c.metadata.get("kind") == "schema_table"
            and c.metadata.get("table") == "Customers"
        )
        assert "CustomerID" in customers_chunk.document
        assert "nchar" in customers_chunk.document.lower()

    def test_relationship_chunks_present(self, chunks) -> None:
        rels = self._by_kind(chunks, "relationship")
        assert len(rels) == 2

    def test_glossary_chunks_present(self, chunks) -> None:
        gloss = self._by_kind(chunks, "glossary")
        # sample profile has 2 glossary terms
        assert len(gloss) == 2
        docs = " ".join(c.document for c in gloss)
        assert "عميل" in docs  # Arabic content preserved

    def test_metric_chunks_present(self, chunks) -> None:
        metrics = self._by_kind(chunks, "metric")
        assert len(metrics) == 2
        docs = " ".join(c.document for c in metrics)
        assert "Revenue" in docs or "الإيرادات" in docs

    def test_example_chunks_present(self, chunks) -> None:
        examples = self._by_kind(chunks, "example")
        assert len(examples) >= 2
        docs = " ".join(c.document for c in examples)
        assert "SELECT" in docs

    def test_table_profile_chunks_present(self, chunks) -> None:
        tp = self._by_kind(chunks, "table_profile")
        names = {c.metadata["table"] for c in tp}
        # sample fixture has Customers + Orders + Order Details per-table profiles
        assert names == {"Customers", "Orders", "Order Details"}

    def test_space_in_table_name_preserved_in_metadata(self, chunks) -> None:
        od = next(
            c for c in chunks
            if c.metadata.get("kind") == "schema_table"
            and c.metadata.get("table") == "Order Details"
        )
        assert od.metadata["table"] == "Order Details"

    def test_table_profile_arabic_content(self, chunks) -> None:
        customers_tp = next(
            c for c in chunks
            if c.metadata.get("kind") == "table_profile"
            and c.metadata.get("table") == "Customers"
        )
        assert "العملاء" in customers_tp.document
