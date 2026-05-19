"""Tests for :mod:`vai_agent.utils.token_counter`."""

from __future__ import annotations

from vai_agent.utils.token_counter import count_tokens


def test_count_tokens_empty() -> None:
    assert count_tokens("") == 0


def test_count_tokens_non_empty() -> None:
    assert count_tokens("hello world") > 0
