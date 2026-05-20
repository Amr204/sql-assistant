from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

_MAX_METADATA_BYTES = 8_192
_MAX_METADATA_KEYS = 32
_MAX_METADATA_DEPTH = 5
_MAX_METADATA_KEY_LEN = 128
_MAX_METADATA_STR_LEN = 2_000


def _validate_metadata_node(value: Any, *, depth: int) -> None:
    if depth > _MAX_METADATA_DEPTH:
        msg = f"metadata exceeds max depth ({_MAX_METADATA_DEPTH})"
        raise ValueError(msg)
    if isinstance(value, dict):
        if len(value) > _MAX_METADATA_KEYS:
            msg = f"metadata exceeds max keys ({_MAX_METADATA_KEYS})"
            raise ValueError(msg)
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metadata keys must be non-empty strings")
            if len(key) > _MAX_METADATA_KEY_LEN:
                raise ValueError("metadata key too long")
            _validate_metadata_node(child, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > _MAX_METADATA_KEYS:
            msg = f"metadata list exceeds max length ({_MAX_METADATA_KEYS})"
            raise ValueError(msg)
        for item in value:
            _validate_metadata_node(item, depth=depth + 1)
        return
    if isinstance(value, str):
        if len(value) > _MAX_METADATA_STR_LEN:
            raise ValueError("metadata string value too long")
        return
    if isinstance(value, (bool, int, float)) or value is None:
        return
    raise ValueError("metadata contains unsupported value type")


class ApiError(BaseModel):
    """Raised when api fails."""
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """ChatRequest body."""
    question: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_metadata_node(value, depth=0)
        encoded = json.dumps(value, default=str, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
            msg = f"metadata exceeds max size ({_MAX_METADATA_BYTES} bytes)"
            raise ValueError(msg)
        return value


class SqlTable(BaseModel):
    """Structured query result for UI rendering (not embedded in ``answer`` text)."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


class ChatResponse(BaseModel):
    """ChatResponse payload."""
    conversation_id: str | None
    request_id: str
    question: str
    answer: str
    sql: str | None = None
    explanation: str | None = None
    confidence: float | None = None
    table: SqlTable | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[ApiError] = Field(default_factory=list)
    execution_ms: int | None = None
    path: str | None = Field(
        default=None,
        description="Which handler produced the reply: 'sql_fast' or 'vanna_agent'.",
    )
    timings: dict[str, int] | None = Field(
        default=None,
        description="Phase timings in ms: intent_ms, context_ms, llm_ms, sql_ms, present_ms, total_ms.",
    )


class StatusResponse(BaseModel):
    """StatusResponse payload."""
    status: str
    app: str
    version: str
    profile_id: str
    profile_ready: bool
    agent_ready: bool
    memory_ready: bool
    tools_ready: bool
    llm_ready: bool
    errors: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    """ProfileResponse payload."""
    profile_id: str
    display_name: str
    dialect: str
    table_count: int
    allowed_groups: list[str]


class ToolDescriptorResponse(BaseModel):
    """ToolDescriptorResponse payload."""
    name: str
    description: str
    access_groups: list[str]
    args_schema: dict[str, Any]


class ToolsListResponse(BaseModel):
    """ToolsListResponse payload."""
    tools: list[ToolDescriptorResponse]
