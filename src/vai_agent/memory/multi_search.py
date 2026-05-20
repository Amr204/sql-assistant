"""Search across profile memory and Vanna agent memory collections."""

from __future__ import annotations

from typing import Any

from vai_agent.memory.memory_factory import AgentMemory


class MultiCollectionSearcher:
    """Search ``memory_<profile>`` and optional ``vanna_agent_<profile>`` collections."""

    def __init__(
        self,
        profile_memory: AgentMemory,
        vanna_memory: AgentMemory | None = None,
    ) -> None:
        self._profile = profile_memory
        self._vanna = vanna_memory

    def search(
        self,
        query: str,
        *,
        n_results: int = 5,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search."""
        hits = self._profile.search(query, n_results=n_results * 2, kind=kind)
        if self._vanna is not None:
            vanna_hits = self._vanna.search(query, n_results=n_results)
            for h in vanna_hits:
                h["source"] = "vanna_agent"
            hits.extend(vanna_hits)
        hits.sort(key=lambda h: float(h.get("distance", 999.0)))
        return hits[:n_results]
