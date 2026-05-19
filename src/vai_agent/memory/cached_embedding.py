"""TTL-cached wrapper for ChromaDB embedding functions."""

from __future__ import annotations

import hashlib
from typing import Any

from cachetools import TTLCache
from chromadb.api.types import EmbeddingFunction


def _embedding_to_list(emb: Any) -> list[float]:
    if hasattr(emb, "tolist"):
        return [float(x) for x in emb.tolist()]
    return [float(x) for x in emb]


class CachedEmbeddingFunction(EmbeddingFunction):
    """Wraps an :class:`EmbeddingFunction` with in-memory LRU+TTL cache."""

    def __init__(
        self,
        inner: EmbeddingFunction,
        *,
        maxsize: int = 1000,
        ttl: int = 3600,
    ) -> None:
        self._inner = inner
        self._cache: TTLCache[str, list[float]] = TTLCache(maxsize=maxsize, ttl=ttl)

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def __call__(self, input: list[str]) -> list[list[float]]:
        results: list[tuple[int, list[float]]] = []
        uncached: list[str] = []
        uncached_idx: list[int] = []

        for i, text in enumerate(input):
            key = self._key(text)
            if key in self._cache:
                results.append((i, self._cache[key]))
            else:
                uncached.append(text)
                uncached_idx.append(i)

        if uncached:
            embeddings = self._inner(uncached)
            for j, (text, emb) in enumerate(zip(uncached, embeddings, strict=True)):
                vec = _embedding_to_list(emb)
                self._cache[self._key(text)] = vec
                results.append((uncached_idx[j], vec))

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        """Chroma 1.5+ uses this when upserting documents."""
        return self(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        """Chroma 1.5+ uses this when querying; must return one vector per query."""
        if isinstance(input, str):
            return self([input])
        return self(list(input))
