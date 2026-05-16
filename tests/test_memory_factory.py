"""Tests for :mod:`vai_agent.memory.memory_factory` and
:func:`vai_agent.memory.seed_memory.seed_profile_memory`.

All tests use a **DummyEmbeddingFunction** that returns trivial unit
vectors, so no ONNX model is downloaded during the test run.  Each test
gets its own ``tmp_path`` directory, guaranteeing test isolation and
verifying that persistence survives a second ``PersistentClient`` call
to the same directory (the "verify persistence after restart" requirement).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from vai_agent.knowledge import ProfileLoader
from vai_agent.memory import (
    AgentMemory,
    ProfileChunk,
    chunk_profile,
    create_memory,
    seed_profile_memory,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


# ---------------------------------------------------------------------------
# DummyEmbeddingFunction — no network, no ONNX download
# ---------------------------------------------------------------------------


class DummyEF:
    """Trivial embedding function: every text maps to a 3-D unit vector.

    The exact vectors don't matter for correctness tests; we just need
    ChromaDB to accept them and return results.
    chromadb >= 1.5 requires __init__ to be defined.
    """

    def __init__(self) -> None:
        pass

    def name(self) -> str:
        """Required by chromadb >= 1.5 for EF identification."""
        return "dummy_ef"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        """Called by chromadb 1.5.x when adding documents."""
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        """Called by chromadb 1.5.x when querying."""
        return self._embed(input)

    @staticmethod
    def _embed(texts: list[str]) -> list[list[float]]:
        return [[float(hash(t) % 100) / 100.0, 0.5, 0.5] for t in texts]


_EF = DummyEF()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture(scope="module")
def sample_chunks(sample_profile):
    return chunk_profile(sample_profile)


# ---------------------------------------------------------------------------
# create_memory
# ---------------------------------------------------------------------------


class TestCreateMemory:
    def test_creates_persist_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "new_dir"
        create_memory(profile_id="test", persist_dir=d, embedding_function=_EF)
        assert d.is_dir()

    def test_returns_agent_memory_and_client(self, tmp_path: Path) -> None:
        import chromadb.api
        mem, client = create_memory(
            profile_id="test", persist_dir=tmp_path, embedding_function=_EF,
        )
        assert isinstance(mem, AgentMemory)
        assert isinstance(client, chromadb.api.ClientAPI)

    def test_collection_name(self, tmp_path: Path) -> None:
        mem, _ = create_memory(
            profile_id="dbnwind", persist_dir=tmp_path, embedding_function=_EF,
        )
        assert mem.collection_name == "memory_dbnwind"

    def test_initial_count_is_zero(self, tmp_path: Path) -> None:
        mem, _ = create_memory(
            profile_id="x", persist_dir=tmp_path, embedding_function=_EF,
        )
        assert mem.count() == 0


# ---------------------------------------------------------------------------
# AgentMemory.seed
# ---------------------------------------------------------------------------


class TestSeed:
    def test_seed_returns_chunk_count(self, tmp_path: Path, sample_chunks) -> None:
        mem, _ = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        written = mem.seed(sample_chunks)
        assert written == len(sample_chunks)

    def test_count_matches_seeded_chunks(self, tmp_path: Path, sample_chunks) -> None:
        mem, _ = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem.seed(sample_chunks)
        assert mem.count() == len(sample_chunks)

    def test_seed_is_idempotent(self, tmp_path: Path, sample_chunks) -> None:
        mem, _ = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem.seed(sample_chunks)
        mem.seed(sample_chunks)  # upsert — must not duplicate
        assert mem.count() == len(sample_chunks)

    def test_seed_empty_list_returns_zero(self, tmp_path: Path) -> None:
        mem, _ = create_memory(
            profile_id="x", persist_dir=tmp_path, embedding_function=_EF,
        )
        assert mem.seed([]) == 0

    def test_seed_partial_update(self, tmp_path: Path) -> None:
        mem, _ = create_memory(
            profile_id="x", persist_dir=tmp_path, embedding_function=_EF,
        )
        first = [ProfileChunk(document="hello", id="x:a:1", metadata={"profile_id": "x", "kind": "test"})]
        second = [ProfileChunk(document="world", id="x:a:2", metadata={"profile_id": "x", "kind": "test"})]
        mem.seed(first)
        mem.seed(second)
        assert mem.count() == 2


# ---------------------------------------------------------------------------
# Persistence across restarts
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_data_survives_new_client(self, tmp_path: Path, sample_chunks) -> None:
        """The key Phase-7 requirement: data written in one process is
        readable by a second PersistentClient pointed at the same directory.
        """
        # First "process": seed
        mem1, _ = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem1.seed(sample_chunks)
        count_after_seed = mem1.count()
        assert count_after_seed == len(sample_chunks)

        # Second "process": open a fresh client, verify count
        mem2, _ = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        assert mem2.count() == count_after_seed

    def test_search_works_after_restart(self, tmp_path: Path) -> None:
        """Search must return results from a second client instance."""
        chunks = [
            ProfileChunk(
                document="Customers table: stores customer master records",
                id="t:schema_table:customers",
                metadata={"profile_id": "t", "kind": "schema_table", "table": "Customers"},
            ),
            ProfileChunk(
                document="Orders table: header records for each purchase order",
                id="t:schema_table:orders",
                metadata={"profile_id": "t", "kind": "schema_table", "table": "Orders"},
            ),
        ]
        mem1, _ = create_memory(
            profile_id="t", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem1.seed(chunks)

        # Open a new client to the same directory
        mem2, _ = create_memory(
            profile_id="t", persist_dir=tmp_path, embedding_function=_EF,
        )
        results = mem2.search("customer records", n_results=2)
        assert len(results) > 0
        assert all("id" in r and "document" in r and "metadata" in r for r in results)


# ---------------------------------------------------------------------------
# AgentMemory.search
# ---------------------------------------------------------------------------


class TestSearch:
    @pytest.fixture()
    def seeded_memory(self, tmp_path: Path) -> AgentMemory:
        chunks = [
            ProfileChunk(
                document="The Customers table holds all buyer records",
                id="p:schema_table:customers",
                metadata={"profile_id": "p", "kind": "schema_table", "table": "Customers"},
            ),
            ProfileChunk(
                document="Glossary: customer means a registered buyer",
                id="p:glossary:customer",
                metadata={"profile_id": "p", "kind": "glossary", "canonical": "customer"},
            ),
            ProfileChunk(
                document="Example: SELECT TOP 10 CustomerID FROM dbo.Customers",
                id="p:example:ex001",
                metadata={"profile_id": "p", "kind": "example", "example_id": "ex001", "difficulty": "simple", "confidence": "high"},
            ),
        ]
        mem, _ = create_memory(
            profile_id="p", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem.seed(chunks)
        return mem

    def test_returns_results(self, seeded_memory: AgentMemory) -> None:
        results = seeded_memory.search("customer")
        assert len(results) > 0

    def test_result_shape(self, seeded_memory: AgentMemory) -> None:
        results = seeded_memory.search("buyer", n_results=3)
        for r in results:
            assert "id" in r
            assert "document" in r
            assert "metadata" in r
            assert "distance" in r

    def test_n_results_respected(self, seeded_memory: AgentMemory) -> None:
        results = seeded_memory.search("buyer", n_results=1)
        assert len(results) == 1

    def test_kind_filter(self, seeded_memory: AgentMemory) -> None:
        results = seeded_memory.search("customer", kind="example")
        assert all(r["metadata"]["kind"] == "example" for r in results)

    def test_search_on_empty_collection_returns_empty(self, tmp_path: Path) -> None:
        mem, _ = create_memory(
            profile_id="empty", persist_dir=tmp_path, embedding_function=_EF,
        )
        results = mem.search("anything")
        assert results == []


# ---------------------------------------------------------------------------
# AgentMemory.reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_data(self, tmp_path: Path, sample_chunks) -> None:
        mem, client = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem.seed(sample_chunks)
        assert mem.count() > 0
        mem.reset(client, "sample")
        assert mem.count() == 0

    def test_data_writable_after_reset(self, tmp_path: Path, sample_chunks) -> None:
        mem, client = create_memory(
            profile_id="sample", persist_dir=tmp_path, embedding_function=_EF,
        )
        mem.seed(sample_chunks)
        mem.reset(client, "sample")
        mem.seed(sample_chunks[:2])
        assert mem.count() == 2


# ---------------------------------------------------------------------------
# seed_profile_memory helper
# ---------------------------------------------------------------------------


class TestSeedProfileMemory:
    def test_seeds_sample_profile(self, tmp_path: Path) -> None:
        result = seed_profile_memory(
            profile_id="sample",
            profiles_root=FIXTURE_ROOT,
            persist_dir=tmp_path,
            embedding_function=_EF,
        )
        assert result["profile_id"] == "sample"
        assert result["chunks_total"] > 0
        assert result["chunks_written"] == result["chunks_total"]
        assert "memory_sample" in result["collection"]

    def test_force_resets_then_seeds(self, tmp_path: Path) -> None:
        seed_profile_memory(
            profile_id="sample",
            profiles_root=FIXTURE_ROOT,
            persist_dir=tmp_path,
            embedding_function=_EF,
        )
        result = seed_profile_memory(
            profile_id="sample",
            profiles_root=FIXTURE_ROOT,
            persist_dir=tmp_path,
            embedding_function=_EF,
            force=True,
        )
        assert result["forced"] is True
        assert result["chunks_written"] > 0

    def test_idempotent_without_force(self, tmp_path: Path) -> None:
        r1 = seed_profile_memory(
            profile_id="sample",
            profiles_root=FIXTURE_ROOT,
            persist_dir=tmp_path,
            embedding_function=_EF,
        )
        r2 = seed_profile_memory(
            profile_id="sample",
            profiles_root=FIXTURE_ROOT,
            persist_dir=tmp_path,
            embedding_function=_EF,
        )
        # Both runs write the same number of chunks (upsert is idempotent).
        assert r1["chunks_written"] == r2["chunks_written"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestSeedMemoryCli:
    """The CLI calls seed_profile_memory, which uses the default embedding
    function unless we patch it.  We patch at the module level so no ONNX
    model is downloaded during tests.
    """

    def test_cli_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import patch

        from vai_agent.cli.seed_memory import main

        with patch(
            "vai_agent.cli.seed_memory.seed_profile_memory",
            side_effect=lambda **kw: seed_profile_memory(
                profile_id=kw["profile_id"],
                profiles_root=kw["profiles_root"],
                persist_dir=kw["persist_dir"],
                embedding_function=_EF,
                force=kw.get("force", False),
            ),
        ):
            out = io.StringIO()
            code = main(
                [
                    "--profile", "sample",
                    "--profiles-root", str(FIXTURE_ROOT),
                    "--persist-dir", str(tmp_path),
                ],
                stdout=out,
            )
        assert code == 0
        text = out.getvalue()
        assert "sample" in text
        assert "chunks_written" in text

    def test_cli_missing_profile_returns_one(self, tmp_path: Path) -> None:
        from vai_agent.cli.seed_memory import main

        err = io.StringIO()
        code = main(
            [
                "--profile", "nonexistent",
                "--profiles-root", str(FIXTURE_ROOT),
                "--persist-dir", str(tmp_path),
            ],
            stderr=err,
        )
        assert code == 1
        assert "FAILED" in err.getvalue()
