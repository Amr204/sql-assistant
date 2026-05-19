"""OpenAI-compatible JSON SQL completion."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vai_agent.config.settings import LlmProvider, Settings

logger = logging.getLogger(__name__)

_shared_client: httpx.AsyncClient | None = None


def _http_client(timeout_seconds: float) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
    return _shared_client


async def close_sql_generator_client() -> None:
    """Close the shared HTTP client (e.g. on app shutdown)."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None


class SqlJsonPayload(BaseModel):
    """Validated LLM JSON payload (SQL must appear only inside this object)."""

    model_config = ConfigDict(extra="ignore")

    sql: str | None = None
    explanation: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("sql", mode="before")
    @classmethod
    def strip_sql(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        s = v.strip()
        return s if s else None


async def generate_sql_json(
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
) -> SqlJsonPayload:
    """Call chat completions; require JSON object; validate with Pydantic."""

    if settings.model_provider is not LlmProvider.openai_compatible:
        return SqlJsonPayload(
            sql=None,
            explanation="MODEL_PROVIDER is not openai_compatible.",
            confidence=0.0,
        )

    key = settings.effective_model_api_key
    if key is None or not key.get_secret_value().strip():
        return SqlJsonPayload(sql=None, explanation="MODEL_API_KEY is not set.", confidence=0.0)

    model = settings.effective_model_name
    if not model:
        return SqlJsonPayload(sql=None, explanation="MODEL_NAME is empty.", confidence=0.0)

    base = settings.effective_model_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    referer = settings.effective_model_http_referer
    if referer:
        headers["HTTP-Referer"] = referer

    body: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    body["response_format"] = {"type": "json_object"}

    client = _http_client(settings.model_http_timeout_seconds)
    resp = await client.post(url, headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("unexpected model provider response shape: %s", data)
        raise ValueError("Invalid completion payload") from exc

    if not isinstance(content, str) or not content.strip():
        return SqlJsonPayload(sql=None, explanation="Empty model response.", confidence=0.0)

    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        return SqlJsonPayload(sql=None, explanation="Model did not return valid JSON.", confidence=0.0)

    if not isinstance(raw, dict):
        return SqlJsonPayload(sql=None, explanation="JSON root must be an object.", confidence=0.0)

    return SqlJsonPayload.model_validate(raw)
