from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SqlTable(BaseModel):
    """Structured query result for UI rendering (not embedded in ``answer`` text)."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


class ChatResponse(BaseModel):
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
    profile_id: str
    display_name: str
    dialect: str
    table_count: int
    allowed_groups: list[str]


class ToolDescriptorResponse(BaseModel):
    name: str
    description: str
    access_groups: list[str]
    args_schema: dict[str, Any]


class ToolsListResponse(BaseModel):
    tools: list[ToolDescriptorResponse]
