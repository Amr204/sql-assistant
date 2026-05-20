"""ToolRegistry — name-keyed catalogue of available tools.

Responsibilities:
* Maintain a name → :class:`ToolBase` mapping.
* Reject duplicate registrations to surface integration mistakes early.
* Filter tools for a given :class:`User` based on the tool's
  ``access_groups`` attribute (an empty tuple = available to all).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from vai_agent.tools.base import ToolBase
from vai_agent.users import User


class ToolRegistry:
    """In-process registry of :class:`ToolBase` instances."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, tool: ToolBase) -> None:
        """Register."""
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def register_all(self, tools: Iterable[ToolBase]) -> None:
        """Register all."""
        for t in tools:
            self.register(t)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, name: str) -> ToolBase | None:
        """Get."""
        return self._tools.get(name)

    def names(self) -> list[str]:
        """Names."""
        return sorted(self._tools)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def __iter__(self) -> Iterator[ToolBase]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    @staticmethod
    def user_can_use(tool: ToolBase, user: User) -> bool:
        """True when *user* is permitted to invoke *tool*.

        A tool with empty :attr:`access_groups` is open to all users.
        Otherwise the user must belong to at least one of the listed
        groups.
        """
        if not tool.access_groups:
            return True
        user_groups = {g.lower() for g in user.groups}
        return any(g.lower() in user_groups for g in tool.access_groups)

    def list_for_user(self, user: User) -> list[ToolBase]:
        """List for user."""
        return [t for t in self._tools.values() if self.user_can_use(t, user)]
