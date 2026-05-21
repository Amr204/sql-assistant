"""SQL fast path orchestration: compact context → JSON SQL → policy → execute → present."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Any

from vanna.capabilities.sql_runner.models import RunSqlToolArgs
from vanna.core.tool.models import ToolContext
from vanna.core.user.models import User as VannaUser

from vai_agent.api.v1.schemas import ApiError, ChatResponse
from vai_agent.config.settings import Settings
from vai_agent.presentation.sql_result_presenter import present_sql_result
from vai_agent.security.audit_log import emit_tool_audit, sql_fingerprint
from vai_agent.sqlfast import memory_learning
from vai_agent.sqlfast.intent_router import needs_enhanced_context
from vai_agent.sqlfast.prompt_builder import (
    build_sql_json_system_prompt,
    build_sql_json_user_prompt,
    compact_enhancer_limits,
)
from vai_agent.sqlfast.sql_generator import generate_sql_json
from vai_agent.users import User as VaiUser
from vai_agent.vai_app.context_enhancer import ContextEnhancer, ContextEnhancerConfig
from vai_agent.vanna_integration.errors import QueryRejectedError
from vai_agent.vanna_integration.runtime import VaiVannaRuntime

logger = logging.getLogger(__name__)

_CONFIDENCE_MIN = 0.5

# Policy codes where we must not delegate to the Vanna agent (unsafe / disallowed patterns).
_NO_FALLBACK_SQL_CODES: frozenset[str] = frozenset(
    {
        "POL001",
        "POL002",
        "POL003",
        "POL004",
        "POL005",
        "POL006",
        "POL007",
        "POL008",
        "POL010",
        "POL011",
        "POL014",
    }
)


class SqlFastOutcome(StrEnum):
    """SqlFastOutcome."""
    SUCCESS = "success"
    REJECT_UNSAFE = "reject_unsafe"
    EXECUTION_FAILED = "execution_failed"
    FALLBACK_VANNA = "fallback_vanna"


@dataclass(frozen=True)
class SqlFastResult:
    """SqlFastResult payload."""
    outcome: SqlFastOutcome
    response: ChatResponse | None
    phase_timings_ms: dict[str, int]


def _sql_blocks_vanna_fallback(sql_codes: set[str]) -> bool:
    return bool(sql_codes & _NO_FALLBACK_SQL_CODES)


def _emit_sql_reject(
    *,
    request_id: str,
    v_user: VannaUser,
    sql: str,
    violations: list[dict[str, Any]],
    error_code: str,
) -> None:
    emit_tool_audit(
        request_id=request_id,
        user_id=v_user.id,
        access_groups=list(v_user.group_memberships),
        tool_name="run_sql",
        decision="rejected",
        sql_hash=sql_fingerprint(sql),
        violations=violations,
        error_code=error_code,
    )


class SqlFastService:
    """End-to-end fast path for clear analytical questions."""

    def __init__(self, runtime: VaiVannaRuntime, settings: Settings) -> None:
        self._runtime = runtime
        self._settings = settings

    async def run(
        self,
        *,
        question: str,
        v_user: VannaUser,
        conversation_id: str | None,
        request_id: str,
    ) -> SqlFastResult:
        """Run."""
        phase: dict[str, int] = {}
        profile = self._runtime.profile

        vai_user = VaiUser(
            id=str(v_user.id),
            email=v_user.email,
            groups=tuple(v_user.group_memberships),
        )

        t_ctx = perf_counter()
        limits = compact_enhancer_limits(self._settings.context_max_tokens)
        if needs_enhanced_context(question):
            limits = {
                "max_tokens": min(4000, self._settings.context_max_tokens),
                "max_tables": 10,
                "max_examples": 5,
                "max_glossary_terms": 12,
                "max_business_rules": 6,
                "memory_search_results": 10,
            }
        enhancer = ContextEnhancer(
            profile,
            memory=self._runtime.chunk_memory,
            config=ContextEnhancerConfig(
                max_tokens=limits["max_tokens"],
                max_tables=limits["max_tables"],
                max_examples=limits["max_examples"],
                max_glossary_terms=limits["max_glossary_terms"],
                max_business_rules=limits["max_business_rules"],
                memory_search_results=limits["memory_search_results"],
            ),
        )
        enhancement = await asyncio.to_thread(enhancer.enhance, question, vai_user)
        phase["context_ms"] = int((perf_counter() - t_ctx) * 1000)

        tool_ctx = ToolContext(
            user=v_user,
            conversation_id=conversation_id or "",
            request_id=request_id,
            agent_memory=self._runtime.vanna.agent_memory,
            metadata={
                "source": "sql_fast_path",
                "question": question,
                "original_question": question,
            },
        )

        t_llm = perf_counter()
        try:
            payload = await generate_sql_json(
                self._settings,
                system_prompt=build_sql_json_system_prompt(),
                user_prompt=build_sql_json_user_prompt(question, enhancement),
            )
        except Exception as exc:
            logger.info("sql fast path LLM failure; falling back to Vanna: %s", exc)
            phase["llm_ms"] = int((perf_counter() - t_llm) * 1000)
            return SqlFastResult(SqlFastOutcome.FALLBACK_VANNA, None, phase)

        phase["llm_ms"] = int((perf_counter() - t_llm) * 1000)

        if payload.sql is None or payload.confidence < _CONFIDENCE_MIN:
            return SqlFastResult(SqlFastOutcome.FALLBACK_VANNA, None, phase)

        sql = payload.sql
        sql_res, pii_res = await self._runtime.policy_runner.validate_tool_sql(sql, tool_ctx)

        if not pii_res.allowed:
            _emit_sql_reject(
                request_id=request_id,
                v_user=v_user,
                sql=sql,
                violations=[v.model_dump() for v in pii_res.violations],
                error_code="pii_policy",
            )
            phase["sql_ms"] = 0
            return SqlFastResult(
                SqlFastOutcome.REJECT_UNSAFE,
                ChatResponse(
                    conversation_id=conversation_id,
                    request_id=request_id,
                    question=question,
                    answer="تم رفض الاستعلام لأسباب تتعلق بحماية البيانات الشخصية.",
                    sql=sql,
                    explanation=payload.explanation or None,
                    confidence=payload.confidence,
                    table=None,
                    warnings=[],
                    errors=[
                        ApiError(
                            code="PII_POLICY",
                            message="Query was rejected by the data-protection policy.",
                            details={"violations": [v.model_dump() for v in pii_res.violations]},
                        ),
                    ],
                    execution_ms=None,
                    path="sql_fast",
                    timings={**phase, "sql_ms": 0, "present_ms": 0},
                ),
                phase,
            )

        if not sql_res.allowed:
            codes = {v.code for v in sql_res.violations}
            if _sql_blocks_vanna_fallback(codes):
                _emit_sql_reject(
                    request_id=request_id,
                    v_user=v_user,
                    sql=sql,
                    violations=[v.model_dump() for v in sql_res.violations],
                    error_code="sql_policy",
                )
                phase["sql_ms"] = 0
                return SqlFastResult(
                    SqlFastOutcome.REJECT_UNSAFE,
                    ChatResponse(
                        conversation_id=conversation_id,
                        request_id=request_id,
                        question=question,
                        answer="تم رفض الاستعلام لأسباب أمنية.",
                        sql=sql,
                        explanation=payload.explanation or None,
                        confidence=payload.confidence,
                        table=None,
                        warnings=[],
                        errors=[
                            ApiError(
                                code="SQL_POLICY",
                                message="Query was rejected by the SQL policy.",
                                details={"violations": [v.model_dump() for v in sql_res.violations]},
                            ),
                        ],
                        execution_ms=None,
                        path="sql_fast",
                        timings={**phase, "sql_ms": 0, "present_ms": 0},
                    ),
                    phase,
                )
            return SqlFastResult(SqlFastOutcome.FALLBACK_VANNA, None, phase)

        t_sql = perf_counter()
        try:
            run = await self._runtime.policy_runner.execute_structured_approved(
                RunSqlToolArgs(sql=sql),
                tool_ctx,
                sql_res,
                pii_res,
            )
        except QueryRejectedError as exc:
            phase["sql_ms"] = int((perf_counter() - t_sql) * 1000)
            logger.warning(
                "sql fast path execution failed: %s",
                exc,
                extra={"sql_preview": sql[:200]},
            )
            err_text = str(exc).strip() or "Query execution failed."
            return SqlFastResult(
                SqlFastOutcome.EXECUTION_FAILED,
                ChatResponse(
                    conversation_id=conversation_id,
                    request_id=request_id,
                    question=question,
                    answer=(
                        "فشل تنفيذ الاستعلام على قاعدة البيانات. "
                        "راجع SQL المُولَّد أدناه — غالبًا يلزم إضافة GROUP BY أو استخدام SUM/COUNT للأعمدة غير المُجمّعة."
                    ),
                    sql=sql,
                    explanation=payload.explanation or None,
                    confidence=payload.confidence,
                    table=None,
                    warnings=[err_text],
                    errors=[
                        ApiError(
                            code="SQL_EXECUTION",
                            message=err_text,
                            details={},
                        ),
                    ],
                    execution_ms=phase["sql_ms"],
                    path="sql_fast",
                    timings={**phase, "present_ms": 0},
                ),
                phase,
            )

        phase["sql_ms"] = int((perf_counter() - t_sql) * 1000)

        t_pr = perf_counter()
        presented = present_sql_result(
            question=question,
            sql=run.sql_executed,
            columns=list(run.columns),
            rows=list(run.rows),
            row_count=run.row_count,
            execution_ms=phase["sql_ms"],
            truncated=run.truncated,
        )
        phase["present_ms"] = int((perf_counter() - t_pr) * 1000)

        await memory_learning.save_fast_path_memory(
            runtime=self._runtime,
            settings=self._settings,
            question=question,
            sql=sql,
            profile_id=profile.meta.profile_id,
            row_count=run.row_count,
            v_user=v_user,
            conversation_id=conversation_id,
            request_id=request_id,
        )

        timings = {
            **phase,
        }
        response = ChatResponse(
            conversation_id=conversation_id,
            request_id=request_id,
            question=question,
            answer=presented.answer,
            sql=presented.sql,
            explanation=presented.explanation,
            confidence=presented.confidence,
            table=presented.table,
            warnings=list(presented.warnings),
            errors=[],
            execution_ms=phase["sql_ms"],
            path="sql_fast",
            timings=timings,
        )
        return SqlFastResult(SqlFastOutcome.SUCCESS, response, phase)
