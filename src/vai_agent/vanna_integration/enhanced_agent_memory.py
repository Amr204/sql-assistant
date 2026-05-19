"""ChromaAgentMemory that tags auto-saved tool usage for profile context search."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vanna.core.tool import ToolContext
from vanna.integrations.chromadb import ChromaAgentMemory


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """ChromaDB metadata must be str | int | float | bool only."""
    out: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)):
            out[str(key)] = value
        elif value is None:
            continue
        else:
            out[str(key)] = str(value)
    return out


class EnhancedChromaAgentMemory(ChromaAgentMemory):
    """Tags successful tool saves with ``kind=auto_learned`` and ``profile_id``."""

    def __init__(self, *args: Any, profile_id: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._profile_id = profile_id

    async def save_tool_usage(
        self,
        question: str,
        tool_name: str,
        args: dict[str, Any],
        context: ToolContext,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(metadata or {})
        merged.setdefault("kind", "auto_learned")
        merged.setdefault("profile_id", self._profile_id)
        merged.setdefault("source", "vanna_save")
        merged.setdefault("saved_at", datetime.now(UTC).isoformat())
        if success and tool_name == "run_sql" and isinstance(args.get("sql"), str):
            merged["sql"] = args["sql"]
        sanitized = _sanitize_metadata(merged)
        await super().save_tool_usage(
            question,
            tool_name,
            args,
            context,
            success=success,
            metadata=sanitized,
        )
