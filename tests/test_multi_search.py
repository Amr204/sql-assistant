"""Tests for :mod:`vai_agent.memory.multi_search`."""

from __future__ import annotations

from unittest.mock import MagicMock

from vai_agent.memory.multi_search import MultiCollectionSearcher


def test_merges_and_sorts_by_distance() -> None:
    profile = MagicMock()
    profile.search.return_value = [
        {"id": "a", "distance": 0.5, "metadata": {}},
        {"id": "b", "distance": 0.1, "metadata": {}},
    ]
    vanna = MagicMock()
    vanna.search.return_value = [
        {"id": "c", "distance": 0.2, "metadata": {}},
    ]
    searcher = MultiCollectionSearcher(profile, vanna)
    hits = searcher.search("query", n_results=2)
    assert len(hits) == 2
    assert hits[0]["id"] == "b"
    assert hits[1]["id"] == "c"
    assert hits[1].get("source") == "vanna_agent"
