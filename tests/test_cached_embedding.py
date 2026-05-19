"""Tests for :mod:`vai_agent.memory.cached_embedding`."""

from __future__ import annotations

import chromadb

from vai_agent.memory.cached_embedding import CachedEmbeddingFunction


class _StubEF:
    def __call__(self, input: list[str]) -> list[list[float]]:
        return [[float(len(t)), 0.0, 0.0] for t in input]


def test_embed_query_returns_list_of_vectors_not_flat_floats() -> None:
    """Chroma 1.5+ expects embed_query to return one embedding per query (batched)."""
    ef = CachedEmbeddingFunction(_StubEF())
    out = ef.embed_query(["hello"])
    assert len(out) == 1
    vec = out[0]
    assert hasattr(vec, "__len__") and len(vec) == 3
    assert not isinstance(vec, float)


def test_chroma_query_with_cached_wrapper() -> None:
    ef = CachedEmbeddingFunction(_StubEF())
    client = chromadb.EphemeralClient()
    col = client.get_or_create_collection("cached_ef_test", embedding_function=ef)
    col.add(ids=["1"], documents=["seed doc"])
    hits = col.query(query_texts=["find me"], n_results=1)
    assert hits["ids"][0]
