"""Metadata bounds on :class:`~vai_agent.api.v1.schemas.ChatRequest`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vai_agent.api.v1.schemas import ChatRequest


def test_metadata_accepts_small_payload() -> None:
    req = ChatRequest(question="hi", metadata={"source": "test"})
    assert req.metadata["source"] == "test"


def test_metadata_rejects_deep_nesting() -> None:
    nested: dict = {"a": {}}
    cur = nested
    for _ in range(10):
        cur["b"] = {}
        cur = cur["b"]
    with pytest.raises(ValidationError):
        ChatRequest(question="hi", metadata=nested)


def test_metadata_rejects_oversized_json() -> None:
    huge = {"k": "x" * 10_000}
    with pytest.raises(ValidationError):
        ChatRequest(question="hi", metadata=huge)
