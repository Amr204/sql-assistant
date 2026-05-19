"""Persistent memory layer (ChromaDB-backed).

Phase 7 deliverables:

* :func:`~vai_agent.memory.chunking.chunk_profile` — converts a loaded
  :class:`Profile` into a flat list of :class:`ProfileChunk` objects.
* :class:`~vai_agent.memory.memory_factory.AgentMemory` — ChromaDB
  wrapper exposing :meth:`seed`, :meth:`search`, :meth:`count`, and
  :meth:`reset`.
* :func:`~vai_agent.memory.memory_factory.create_memory` — factory that
  opens (or creates) a persistent collection.
* :func:`~vai_agent.memory.seed_memory.seed_profile_memory` — high-level
  helper used by both the CLI script and tests.
"""

from vai_agent.memory.chunking import ProfileChunk, chunk_profile
from vai_agent.memory.memory_factory import AgentMemory, AgentMemoryError, create_memory
from vai_agent.memory.seed_memory import seed_profile_memory

__all__ = [
    "AgentMemory",
    "AgentMemoryError",
    "ProfileChunk",
    "chunk_profile",
    "create_memory",
    "seed_profile_memory",
]
