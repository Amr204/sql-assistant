"""ChromaDB-backed persistent agent memory.

:class:`AgentMemory` wraps a ``chromadb.PersistentClient`` and one
named collection per profile.  All data written to it survives process
restarts — the client re-opens the same SQLite+HNSW files on the next
call to :func:`create_memory`.

Embedding function
------------------
By default ``AgentMemory`` uses ChromaDB's built-in
``DefaultEmbeddingFunction`` (all-MiniLM-L6-v2 via ONNX), which is
downloaded and cached on first use at::

    ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/

In tests and offline environments, callers may pass a custom
``embedding_function`` that returns pre-computed vectors — see
``tests/test_memory_factory.py`` for the lightweight dummy used there.

Collection naming
-----------------
Each profile gets its own collection: ``memory_<profile_id>``.  Using
separate collections keeps similarity searches scoped to the right
database profile without requiring ``where`` filters on every query.

Public API
----------
* :meth:`seed`         — upsert a list of :class:`ProfileChunk` objects.
* :meth:`search`       — vector-similarity search; returns ranked hits.
* :meth:`count`        — number of documents in the collection.
* :meth:`collection_name` — the underlying ChromaDB collection name.
* :meth:`reset`        — delete and recreate the collection (useful for
                          re-seeding from scratch).
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import EmbeddingFunction

from vai_agent.memory.chunking import ProfileChunk

logger = logging.getLogger(__name__)

# Default batch size for upsert calls.  Chromadb has no hard limit but
# large batches can be slow on constrained hardware.
_UPSERT_BATCH = 100


class MemoryError(Exception):
    """Raised when the memory layer encounters an unrecoverable error."""


def _collection_name(profile_id: str) -> str:
    """Return the ChromaDB collection name for *profile_id*."""
    # Collection names must match [a-zA-Z0-9_-]{3,63} in ChromaDB.
    safe = profile_id.replace(" ", "_").replace(".", "_")
    return f"memory_{safe}"


class AgentMemory:
    """Persistent vector store for one profile.

    Instantiate via :func:`create_memory` rather than directly.
    """

    def __init__(self, collection: chromadb.Collection) -> None:
        self._col = collection

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def collection_name(self) -> str:
        return self._col.name

    @property
    def chroma_collection(self) -> chromadb.Collection:
        """Underlying Chroma collection (for Vanna :class:`~vanna.capabilities.agent_memory.AgentMemory` adapters)."""

        return self._col

    def count(self) -> int:
        """Return the number of documents currently stored."""
        return self._col.count()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def seed(self, chunks: list[ProfileChunk]) -> int:
        """Upsert *chunks* into the collection.

        Uses ``upsert`` so the method is idempotent: calling it twice
        with the same chunks produces the same result as calling it once.

        Returns the number of chunks written.
        """
        if not chunks:
            return 0

        total = 0
        for i in range(0, len(chunks), _UPSERT_BATCH):
            batch = chunks[i : i + _UPSERT_BATCH]
            self._col.upsert(
                documents=[c.document for c in batch],
                ids=[c.id for c in batch],
                metadatas=[c.metadata for c in batch],
            )
            total += len(batch)
            logger.debug(
                "memory: upserted batch",
                extra={"start": i, "count": len(batch), "total_so_far": total},
            )

        logger.info(
            "memory: seed complete",
            extra={
                "collection": self._col.name,
                "chunks_written": total,
            },
        )
        return total

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        n_results: int = 5,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over stored chunks.

        Parameters
        ----------
        query:
            The natural-language query string to embed and search.
        n_results:
            Maximum number of results to return.
        kind:
            Optional filter on the ``kind`` metadata field (e.g.
            ``"example"``, ``"glossary"``, ``"schema_table"``).

        Returns
        -------
        list[dict]
            Each dict has keys ``id``, ``document``, ``metadata``,
            ``distance``.  Sorted nearest-first.
        """
        count = self.count()
        if count == 0:
            return []

        # ChromaDB raises if n_results > collection size.
        effective_n = min(n_results, count)
        where: dict[str, Any] | None = {"kind": kind} if kind else None

        try:
            results = self._col.query(
                query_texts=[query],
                n_results=effective_n,
                where=where,
            )
        except Exception as exc:
            raise MemoryError(f"search failed: {exc}") from exc

        hits: list[dict[str, Any]] = []
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]
        for doc_id, doc, meta, dist in zip(ids, docs, metas, distances, strict=True):
            hits.append({
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "distance": dist,
            })
        return hits

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def reset(self, client: chromadb.api.ClientAPI, profile_id: str) -> None:
        """Delete and recreate the collection, removing all stored data."""
        name = self._col.name
        with contextlib.suppress(Exception):
            client.delete_collection(name)
        self._col = client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "profile_id": profile_id},
        )
        logger.info("memory: collection reset", extra={"collection": name})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_memory(
    *,
    profile_id: str,
    persist_dir: str | Path,
    embedding_function: EmbeddingFunction | None = None,
) -> tuple[AgentMemory, chromadb.api.ClientAPI]:
    """Open (or create) a persistent ChromaDB store for *profile_id*.

    Parameters
    ----------
    profile_id:
        Identifies the database profile; used to derive the collection
        name (``memory_<profile_id>``).
    persist_dir:
        Directory on disk where ChromaDB writes its SQLite files and
        vector index.  Created automatically if absent.
    embedding_function:
        Optional custom embedding function.  When ``None``, ChromaDB's
        ``DefaultEmbeddingFunction`` (all-MiniLM-L6-v2) is used.
        Pass a lightweight dummy in tests to avoid network downloads.

    Returns
    -------
    (AgentMemory, chromadb.Client)
        The memory wrapper and the raw client (so callers can call
        :meth:`AgentMemory.reset` without needing to re-open the client).
    """
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_dir))
    cname = _collection_name(profile_id)

    col_kwargs: dict[str, Any] = {
        "name": cname,
        "metadata": {"hnsw:space": "cosine", "profile_id": profile_id},
    }
    if embedding_function is not None:
        col_kwargs["embedding_function"] = embedding_function

    collection = client.get_or_create_collection(**col_kwargs)
    logger.info(
        "memory: opened collection",
        extra={
            "profile_id": profile_id,
            "collection": cname,
            "persist_dir": str(persist_dir),
            "count": collection.count(),
        },
    )
    return AgentMemory(collection), client
