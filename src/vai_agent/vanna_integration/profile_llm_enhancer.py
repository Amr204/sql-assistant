"""Inject :class:`~vai_agent.vai_app.context_enhancer.ContextEnhancer` output into Vanna LLM prompts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from vanna.core.enhancer import LlmContextEnhancer
from vanna.core.llm.models import LlmMessage
from vanna.core.user.models import User as VannaUser

from vai_agent.users import User as VaiUser
from vai_agent.vai_app.context_enhancer import ContextEnhancer

if TYPE_CHECKING:
    pass


def _sql_server_generation_rules() -> str:
    from vai_agent.config.settings import get_settings

    lines = [
        "## Rules (assistant behaviour)",
        "- For count questions, answer with the numeric result directly in natural language; "
        "do not dump raw column headers and values as CSV-like text.",
        "- Do not mention CSV files, export paths, or internal filenames (including `query_results_`).",
        "- Do not suggest visualization, charts, or `visualize_data` unless the user explicitly asks for a chart.",
        '- Do not say "Test 1", "Test 2", or similar placeholders.',
        "- Prefer a concise business answer; rely on the tool layer for structured tabular data when applicable.",
        "## Tool-selection fast path",
        "- When the user clearly asks for retrievable data (counts, lists, rankings, aggregates, JOINs) "
        "and table/column intent is unambiguous, use **run_sql** only and finish with a short answer.",
        "- Call **explain_schema** or **profile_search** only when the question is ambiguous about which "
        "tables/columns apply or needs glossary clarification.",
        "## SQL Server generation rules",
        "- Never use reserved or misleading column aliases such as RowCount (any casing). "
        "For COUNT aggregates use alias [record_count], e.g. "
        "`SELECT COUNT(*) AS [record_count] FROM dbo.MyTable`.",
        "- Never mention internal CSV export filenames or paths containing `query_results_` "
        "unless the user explicitly asks for a file export.",
        "- Answer count questions with the numeric result directly; do not prefix with "
        "\"Test 1\" or similar placeholders.",
    ]
    s = get_settings()
    if not s.enable_visualization_tools:
        lines.append(
            "- Do not call visualization or chart tools unless the user explicitly asks "
            "for a chart, graph, or visualization.",
        )
    return "\n".join(lines)


class ProfileLlmContextEnhancer(LlmContextEnhancer):
    """Adds profile-derived context (schema, glossary, security) to the system prompt."""

    _SQL_FOCUSED_PREFIX = (
        "You are a SQL query assistant. Your PRIMARY task is to generate accurate T-SQL SELECT queries. "
        "When the user asks a data question, generate a SQL query using the run_sql tool. "
        "Study the examples and schema context carefully before writing SQL. "
        "Never use SELECT *. Always use explicit column names. Use TOP for row limits.\n\n"
    )
    _GENERAL_ASSISTANT_PREFIX = (
        "You are a helpful data assistant. Use tools when needed; keep answers concise.\n\n"
    )

    def __init__(self, enhancer: ContextEnhancer) -> None:
        self._enhancer = enhancer

    @staticmethod
    def _sql_prefix(question: str) -> str:
        """Inject SQL-focused guidance only for data-retrieval questions."""
        data_indicators = {
            "كم", "عدد", "اعرض", "list", "show", "count", "top", "how many",
        }
        q_lower = question.lower()
        if any(ind in q_lower for ind in data_indicators):
            return ProfileLlmContextEnhancer._SQL_FOCUSED_PREFIX
        return ProfileLlmContextEnhancer._GENERAL_ASSISTANT_PREFIX

    async def enhance_system_prompt(
        self, system_prompt: str, user_message: str, user: VannaUser
    ) -> str:
        vai_user = VaiUser(
            id=user.id,
            email=user.email,
            groups=tuple(user.group_memberships),
        )

        def _build() -> object:
            return self._enhancer.enhance(user_message, vai_user)

        result = await asyncio.to_thread(_build)
        block = result.context_text.strip()
        if not block:
            return f"{system_prompt}\n\n{_sql_server_generation_rules()}"

        prefix = self._sql_prefix(user_message)
        return (
            f"{system_prompt}\n\n"
            f"{prefix}## Retrieved profile context\n{block}\n\n{_sql_server_generation_rules()}"
        )

    async def enhance_user_messages(
        self, messages: list[LlmMessage], user: VannaUser
    ) -> list[LlmMessage]:
        return messages
