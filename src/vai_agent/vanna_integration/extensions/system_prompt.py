"""System prompt helpers for the SQL assistant.

Stable assistant behaviour and task routing live here. Profile-derived RAG
(schema, glossary, examples) is assembled separately by
:class:`~vai_agent.vanna_integration.profile_llm_enhancer.ProfileLlmContextEnhancer`.
"""

from __future__ import annotations

_SQL_FOCUSED_PREFIX = (
    "You are a SQL query assistant. Your PRIMARY task is to generate accurate T-SQL SELECT queries. "
    "When the user asks a data question, generate a SQL query using the run_sql tool. "
    "Study the examples and schema context carefully before writing SQL. "
    "Never use SELECT *. Always use explicit column names. Use TOP for row limits.\n\n"
)
_GENERAL_ASSISTANT_PREFIX = (
    "You are a helpful data assistant. Use tools when needed; keep answers concise.\n\n"
)
_DATA_QUESTION_INDICATORS = frozenset({
    "كم", "عدد", "اعرض", "list", "show", "count", "top", "how many",
})


def base_sql_assistant_prompt() -> str:
    """High-level identity rules (reserved for future SystemPromptBuilder wiring)."""

    return "\n".join([
        "You are a secure SQL assistant for Microsoft SQL Server.",
        "Use tools to answer data questions.",
        "Never generate or execute non-SELECT statements.",
        "Never expose secrets, connection strings, or internal infrastructure details.",
        "Prefer concise business answers after tool execution.",
    ])


def task_prefix_for_question(question: str) -> str:
    """Return SQL-focused or general task guidance based on the user question."""

    q_lower = question.lower()
    if any(ind in q_lower for ind in _DATA_QUESTION_INDICATORS):
        return _SQL_FOCUSED_PREFIX
    return _GENERAL_ASSISTANT_PREFIX


def sql_server_generation_rules() -> str:
    """Stable behaviour and SQL-generation rules appended to the system prompt."""

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
    return "\n".join(lines)
