"""Profile → ChromaDB seeding logic.

This module provides the callable used by both ``scripts/seed_memory.py``
(CLI) and future API endpoints that trigger re-seeding.

Entry point: :func:`seed_profile_memory`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from chromadb.api.types import EmbeddingFunction

from vai_agent.knowledge import ProfileLoader
from vai_agent.memory.chunking import chunk_profile
from vai_agent.memory.memory_factory import create_memory

logger = logging.getLogger(__name__)


def seed_profile_memory(
    *,
    profile_id: str,
    profiles_root: str | Path,
    persist_dir: str | Path,
    embedding_function: EmbeddingFunction | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Load *profile_id*, chunk it, and upsert into ChromaDB.

    Parameters
    ----------
    profile_id:
        The profile directory name under *profiles_root*.
    profiles_root:
        Parent directory of all profile directories.
    persist_dir:
        ChromaDB persistence directory.
    embedding_function:
        Custom embedding function (useful for tests / offline envs).
    force:
        When ``True``, the collection is wiped before seeding (full
        re-seed).  When ``False`` (default), existing chunks are
        upserted — this is idempotent and cheaper for incremental updates.

    Returns
    -------
    dict with keys: ``profile_id``, ``chunks_total``, ``chunks_written``,
    ``collection``, ``forced``.
    """
    loader = ProfileLoader(profiles_root)
    profile = loader.load(profile_id)
    chunks = chunk_profile(profile)

    memory, client = create_memory(
        profile_id=profile_id,
        persist_dir=persist_dir,
        embedding_function=embedding_function,
    )

    if force:
        logger.info(
            "seed_memory: force reset requested",
            extra={"profile_id": profile_id},
        )
        memory.reset(client, profile_id)

    written = memory.seed(chunks)

    return {
        "profile_id": profile_id,
        "chunks_total": len(chunks),
        "chunks_written": written,
        "collection": memory.collection_name,
        "forced": force,
    }
