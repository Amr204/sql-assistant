"""Base classes and result types shared by every agent tool."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from vai_agent.users import User


class ToolResult(BaseModel):
    """Uniform result envelope returned by every tool.

    The shape is deliberately FastAPI-serialisable: plain ``dict`` for
    ``data`` and ``metadata`` so the same object can be returned from
    HTTP endpoints without extra conversion.
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    tool: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolBase(ABC):
    """Abstract base class for all tools.

    Subclasses must define :attr:`name`, :attr:`description`,
    :attr:`args_model`, and may override :attr:`access_groups`. An empty
    :attr:`access_groups` tuple means "any authenticated user may invoke".

    The :meth:`execute` method is synchronous; FastAPI runs it in a
    worker thread automatically. Sync code keeps tests and tool authors
    simple and matches the synchronous nature of ``pyodbc``.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    access_groups: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def execute(self, args: BaseModel, user: User) -> ToolResult:
        """Run the tool with validated *args* on behalf of *user*."""

    # ------------------------------------------------------------------
    # Convenience helpers for subclasses
    # ------------------------------------------------------------------

    def _ok(self, data: dict[str, Any], **metadata: Any) -> ToolResult:
        return ToolResult(success=True, tool=self.name, data=data, metadata=metadata)

    def _fail(self, error: str, **metadata: Any) -> ToolResult:
        return ToolResult(success=False, tool=self.name, error=error, metadata=metadata)
