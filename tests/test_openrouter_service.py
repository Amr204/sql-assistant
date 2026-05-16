"""Tests for OpenRouter / LLM wiring."""

from __future__ import annotations

import httpx
import pytest
from httpx import MockTransport
from pydantic import SecretStr

from vai_agent.config.settings import LlmProvider, Settings
from vai_agent.llm import OpenRouterChatService, build_chat_completion_client
from vai_agent.llm.base import ChatMessage
from vai_agent.llm.errors import LlmUpstreamError


def test_openrouter_chat_completion_parses_response() -> None:
    """Happy path parsing of OpenAI-style JSON payloads."""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert "/chat/completions" in str(request.url)
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {"message": {"content": "  answer  "}, "finish_reason": "stop"}
                ],
                "model": "provider/model-alias",
            },
        )

    client = httpx.Client(transport=MockTransport(_handler))
    svc = OpenRouterChatService(api_key="k", model="m", http_client=client)

    try:
        got = svc.chat_completion(
            (ChatMessage(role="user", content="hello"),),
        )

        assert got.content == "answer"
        assert got.model_used == "provider/model-alias"
        assert got.finish_reason == "stop"
    finally:
        svc.close()


def test_openrouter_upstream_error_when_empty_choice() -> None:
    transport = MockTransport(
        lambda _r: httpx.Response(200, json={"choices": []}),
    )
    client = httpx.Client(transport=transport)
    svc = OpenRouterChatService(api_key="k", model="m", http_client=client)
    try:
        with pytest.raises(LlmUpstreamError):
            svc.chat_completion((ChatMessage(role="user", content="hello"),))
    finally:
        svc.close()


def test_build_chat_completion_returns_none_when_provider_none() -> None:
    settings = Settings(
        llm_provider=LlmProvider.none,
        _env_file=None,  # type: ignore[call-arg]
    )
    assert build_chat_completion_client(settings) is None


def test_build_chat_completion_returns_service_when_openrouter_configured() -> None:
    settings = Settings(
        llm_provider=LlmProvider.openrouter,
        openrouter_api_key=SecretStr("secret"),
        openrouter_model="vendor/model-name",
        _env_file=None,  # type: ignore[call-arg]
    )
    svc = build_chat_completion_client(settings)
    assert isinstance(svc, OpenRouterChatService)
    svc.close()


def test_build_chat_completion_returns_none_without_api_key() -> None:
    settings = Settings(
        llm_provider=LlmProvider.openrouter,
        openrouter_model="x",
        openrouter_api_key=None,
        _env_file=None,  # type: ignore[call-arg]
    )
    assert build_chat_completion_client(settings) is None


def test_build_chat_completion_returns_none_without_model() -> None:
    settings = Settings(
        llm_provider=LlmProvider.openrouter,
        openrouter_api_key=SecretStr("k"),
        openrouter_model="  ",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert build_chat_completion_client(settings) is None
