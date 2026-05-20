from __future__ import annotations

import json
import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from vanna.servers.base import ChatRequest as VannaChatRequest

from vai_agent.api.deps import build_request_context, require_runtime
from vai_agent.api.v1.schemas import ApiError, ChatRequest, ChatResponse
from vai_agent.audit.activity_recorder import (
    ActivityEvent,
    get_activity_recorder,
    safe_record_activity,
)
from vai_agent.config.settings import get_settings
from vai_agent.presentation.sql_result_presenter import (
    clean_assistant_text,
    present_sql_result,
)
from vai_agent.security.prompt_injection import check_prompt_injection
from vai_agent.sqlfast.intent_router import ChatPath, route_intent
from vai_agent.sqlfast.service import SqlFastOutcome, SqlFastService
from vai_agent.users import UserResolutionError
from vai_agent.vanna_integration.guarded_chat import GuardedChatHandler

router = APIRouter(prefix="/chat", tags=["chat"])


def extract_answer(payload: dict[str, Any]) -> str:
    """Extract assistant text from a Vanna or legacy payload dict."""
    for key in ("answer", "message", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("answer", "message", "text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    chunks = payload.get("chunks")
    if isinstance(chunks, list):
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            simple = chunk.get("simple")
            if isinstance(simple, dict):
                text = simple.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    return ""


def _extract_sql_tables(raw: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    sql = raw.get("sql")
    sql_out: str | None = sql if isinstance(sql, str) else None
    tables = raw.get("tables")
    tables_out: list[dict[str, Any]] = []
    if isinstance(tables, list):
        for item in tables:
            if isinstance(item, dict):
                tables_out.append(item)
    return sql_out, tables_out


def _extract_rows_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    _, from_tables = _extract_sql_tables(raw)
    if from_tables:
        return from_tables
    chunks = raw.get("chunks")
    if not isinstance(chunks, list):
        return []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for key in ("rich", "simple"):
            block = chunk.get(key)
            if not isinstance(block, dict):
                continue
            data = block.get("data")
            if not isinstance(data, dict):
                continue
            rows = data.get("rows")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows
            inner_rows = data.get("data")
            if isinstance(inner_rows, list) and inner_rows and isinstance(inner_rows[0], dict):
                return inner_rows
    return []


def _extract_last_vai_structured_sql(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse last VAI dataframe chunk (``_vai_sql`` in ``column_types``)."""

    chunks = raw.get("chunks")
    if not isinstance(chunks, list):
        return None
    last: dict[str, Any] | None = None
    for ch in chunks:
        if not isinstance(ch, dict):
            continue
        rich = ch.get("rich")
        if not isinstance(rich, dict) or rich.get("type") != "dataframe":
            continue
        inner = rich.get("data")
        if not isinstance(inner, dict):
            continue
        ct = inner.get("column_types")
        if not isinstance(ct, dict):
            continue
        sql_m = ct.get("_vai_sql")
        if not isinstance(sql_m, str) or not sql_m.strip():
            continue
        rows_inner = inner.get("data")
        cols = inner.get("columns")
        if not isinstance(rows_inner, list):
            rows_inner = []
        if not isinstance(cols, list):
            cols = []
        trunc_raw = ct.get("_vai_truncated", "0")
        truncated = str(trunc_raw).strip() in ("1", "true", "True")
        ms_raw = ct.get("_vai_ms", "")
        try:
            tool_ms = int(str(ms_raw)) if str(ms_raw).strip() else None
        except ValueError:
            tool_ms = None
        last = {
            "sql": sql_m.strip(),
            "columns": [str(c) for c in cols],
            "rows": [dict(r) for r in rows_inner if isinstance(r, dict)],
            "row_count": len(rows_inner) if isinstance(rows_inner, list) else 0,
            "truncated": truncated,
            "execution_ms": tool_ms,
        }
    return last


def _extract_truncated_from_raw(raw: dict[str, Any]) -> bool:
    chunks = raw.get("chunks")
    if not isinstance(chunks, list):
        return False
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for key in ("rich", "simple"):
            block = chunk.get(key)
            if not isinstance(block, dict):
                continue
            data = block.get("data")
            if isinstance(data, dict) and data.get("truncated") is True:
                return True
    return False


def _best_sql(raw: dict[str, Any], sql_hint: str | None) -> str | None:
    if isinstance(sql_hint, str) and sql_hint.strip():
        return sql_hint
    ex = raw.get("sql_executed")
    if isinstance(ex, str) and ex.strip():
        return ex
    return None


def _merge_wall_timings(resp: ChatResponse, *, intent_ms: int, t0: float) -> ChatResponse:
    total_ms = int((perf_counter() - t0) * 1000)
    merged = {**(resp.timings or {}), "intent_ms": intent_ms, "total_ms": total_ms}
    return resp.model_copy(update={"timings": merged})


@router.post("", response_model=ChatResponse)
async def ask(body: ChatRequest, request: Request) -> ChatResponse:
    """Handle POST /api/v1/chat (SQL fast path or guarded Vanna agent)."""
    runtime = require_runtime(request)
    settings = get_settings()
    request_id = uuid.uuid4().hex
    t0 = perf_counter()
    recorder = get_activity_recorder()
    profile_id = runtime.profile.meta.profile_id
    db_name = runtime.profile.meta.database_name

    injection = check_prompt_injection(body.question)
    if not injection.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "PROMPT_REJECTED",
                "message": "The question was rejected by safety checks.",
                "reason": injection.reason,
            },
        )

    metadata = {
        **body.metadata,
        "request_id": request_id,
        "original_question": body.question,
        "source": "web_ui",
        "api_version": "v1",
        "remote_ip": request.client.host if request.client else "unknown",
    }

    if await request.is_disconnected():
        return ChatResponse(
            conversation_id=body.conversation_id or "",
            request_id=request_id,
            question=body.question,
            answer="",
            errors=[ApiError(code="CANCELLED", message="Request was cancelled by the user.")],
            path="vanna_agent",
        )

    rc = build_request_context(request, metadata)
    user_id = ""
    user_email = ""
    user_groups = ""
    v_user = None
    try:
        v_user = await runtime.vanna.user_resolver.resolve_user(rc)
        user_id = str(v_user.id)
        user_email = v_user.email or ""
        user_groups = ",".join(v_user.group_memberships)
    except UserResolutionError:
        v_user = None

    if v_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "User authentication required."},
        )

    safe_record_activity(
        recorder,
        ActivityEvent(
            request_id=request_id,
            event_type="request.received",
            status="received",
            conversation_id=body.conversation_id,
            source="web_ui",
            route="/api/v1/chat",
            user_id=user_id,
            user_email=user_email,
            user_groups=user_groups,
            profile_id=profile_id,
            db_name=db_name,
            question=body.question,
            model_provider=settings.audit_model_provider,
            model_name=settings.effective_model_name,
        ),
    )

    t_intent = perf_counter()
    use_sql_fast = (
        settings.sql_fast_path_enabled
        and v_user is not None
        and route_intent(body.question) is ChatPath.SQL_FAST
    )
    intent_ms = int((perf_counter() - t_intent) * 1000)

    if use_sql_fast:
        fast = await SqlFastService(runtime, settings).run(
            question=body.question,
            v_user=v_user,
            conversation_id=body.conversation_id,
            request_id=request_id,
        )
        if fast.outcome is SqlFastOutcome.SUCCESS and fast.response is not None:
            out = _merge_wall_timings(fast.response, intent_ms=intent_ms, t0=t0)
            timings_json = json.dumps(out.timings or {})
            safe_record_activity(
                recorder,
                ActivityEvent(
                    request_id=request_id,
                    event_type="response.sent",
                    status="success",
                    conversation_id=out.conversation_id,
                    route="/api/v1/chat",
                    user_id=user_id,
                    user_email=user_email,
                    user_groups=user_groups,
                    profile_id=profile_id,
                    db_name=db_name,
                    question=body.question,
                    tool_name="sql_fast",
                    generated_sql=out.sql or "",
                    executed_sql=out.sql or "",
                    row_count=(out.table.row_count if out.table is not None else 0),
                    duration_ms=out.timings.get("total_ms") if out.timings else None,
                    answer_preview=out.answer,
                    model_provider=settings.audit_model_provider,
                    model_name=settings.effective_model_name,
                    timings_json=timings_json,
                ),
            )
            return out

        if fast.outcome is SqlFastOutcome.REJECT_UNSAFE and fast.response is not None:
            out = _merge_wall_timings(fast.response, intent_ms=intent_ms, t0=t0)
            timings_json = json.dumps(out.timings or {})
            safe_record_activity(
                recorder,
                ActivityEvent(
                    request_id=request_id,
                    event_type="response.sent",
                    status="rejected",
                    conversation_id=out.conversation_id,
                    route="/api/v1/chat",
                    user_id=user_id,
                    user_email=user_email,
                    user_groups=user_groups,
                    profile_id=profile_id,
                    db_name=db_name,
                    question=body.question,
                    tool_name="sql_fast",
                    generated_sql=out.sql or "",
                    executed_sql="",
                    row_count=0,
                    duration_ms=out.timings.get("total_ms") if out.timings else None,
                    answer_preview=out.answer,
                    model_provider=settings.audit_model_provider,
                    model_name=settings.effective_model_name,
                    timings_json=timings_json,
                ),
            )
            return out

    vanna_request = VannaChatRequest(
        message=body.question,
        conversation_id=body.conversation_id,
        request_id=request_id,
        request_context=rc,
        metadata=metadata,
    )

    handler = GuardedChatHandler(
        runtime.vanna,
        settings,
        disconnect_check=request.is_disconnected,
    )
    try:
        response = await handler.handle_poll(vanna_request)
    except HTTPException as exc:
        safe_record_activity(
            recorder,
            ActivityEvent(
                request_id=request_id,
                event_type="error",
                status="error",
                conversation_id=body.conversation_id,
                route="/api/v1/chat",
                user_id=user_id,
                user_email=user_email,
                user_groups=user_groups,
                profile_id=profile_id,
                db_name=db_name,
                question=body.question,
                error_type="HTTPException",
                error_message=str(exc.detail),
                duration_ms=int((perf_counter() - t0) * 1000),
                model_provider=settings.audit_model_provider,
                model_name=settings.effective_model_name,
            ),
        )
        raise
    except Exception as exc:
        safe_record_activity(
            recorder,
            ActivityEvent(
                request_id=request_id,
                event_type="error",
                status="error",
                conversation_id=body.conversation_id,
                route="/api/v1/chat",
                user_id=user_id,
                user_email=user_email,
                user_groups=user_groups,
                profile_id=profile_id,
                db_name=db_name,
                question=body.question,
                error_type=type(exc).__name__,
                error_message=str(exc),
                duration_ms=int((perf_counter() - t0) * 1000),
                model_provider=settings.audit_model_provider,
                model_name=settings.effective_model_name,
            ),
        )
        raise

    raw = response.model_dump(mode="json")
    sql_hint, tables_hint = _extract_sql_tables(raw)
    structured = _extract_last_vai_structured_sql(raw)
    rows = structured["rows"] if structured else _extract_rows_from_raw(raw)
    sql_out = structured["sql"] if structured else _best_sql(raw, sql_hint)
    truncated = structured["truncated"] if structured else _extract_truncated_from_raw(raw)
    t_wall_done = perf_counter()
    execution_ms_wall = int((t_wall_done - t0) * 1000)
    tool_ms = structured.get("execution_ms") if structured else None
    execution_ms = int(tool_ms) if isinstance(tool_ms, int) else execution_ms_wall

    warnings: list[str] = []
    explanation: str | None = None
    confidence: float | None = None
    table = None

    if rows and sql_out:
        if structured and structured.get("columns"):
            cols = list(structured["columns"])
        elif rows:
            cols = list(rows[0].keys())
        else:
            cols = []
        presented = present_sql_result(
            question=body.question,
            sql=sql_out,
            columns=cols,
            rows=rows,
            row_count=len(rows),
            execution_ms=execution_ms,
            truncated=truncated,
        )
        answer = presented.answer
        sql_out = presented.sql
        explanation = presented.explanation
        confidence = presented.confidence
        table = presented.table
        warnings = list(presented.warnings)
    else:
        fallback = clean_assistant_text(extract_answer(raw))
        answer = fallback if fallback else "(No text reply)"
        if tables_hint and not rows:
            warnings.append("Structured rows missing from agent payload; table omitted.")

    duration_ms = execution_ms
    timings_agent = {
        "intent_ms": intent_ms,
        "context_ms": 0,
        "llm_ms": 0,
        "sql_ms": execution_ms,
        "present_ms": 0,
        "total_ms": execution_ms_wall,
    }
    safe_record_activity(
        recorder,
        ActivityEvent(
            request_id=request_id,
            event_type="response.sent",
            status="success",
            conversation_id=response.conversation_id,
            route="/api/v1/chat",
            user_id=user_id,
            user_email=user_email,
            user_groups=user_groups,
            profile_id=profile_id,
            db_name=db_name,
            question=body.question,
            duration_ms=duration_ms,
            answer_preview=answer,
            model_provider=settings.audit_model_provider,
            model_name=settings.effective_model_name,
            timings_json=json.dumps(timings_agent),
        ),
    )

    return ChatResponse(
        conversation_id=response.conversation_id,
        request_id=response.request_id or request_id,
        question=body.question,
        answer=answer,
        sql=sql_out,
        explanation=explanation,
        confidence=confidence,
        table=table,
        warnings=warnings,
        errors=[],
        execution_ms=execution_ms,
        path="vanna_agent",
        timings=timings_agent,
    )
