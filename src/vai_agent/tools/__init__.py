"""Agent tools (Phase 6).

Each tool inherits from :class:`ToolBase`, declares a Pydantic
``args_model``, declares the ``access_groups`` allowed to invoke it,
and returns a :class:`ToolResult`. Tools never raise unexpected
exceptions to callers — failures are wrapped in :class:`ToolResult`
with ``success=False`` and a sanitised ``error`` string.
"""

from vai_agent.tools.base import ToolBase, ToolResult
from vai_agent.tools.explain_schema_tool import ExplainSchemaTool
from vai_agent.tools.profile_search_tool import ProfileSearchTool

__all__ = [
    "ExplainSchemaTool",
    "ProfileSearchTool",
    "ToolBase",
    "ToolResult",
]
