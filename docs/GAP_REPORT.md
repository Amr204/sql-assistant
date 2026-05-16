# GAP_REPORT — Vanna alignment (May 2026)

## What `vai-prompt.txt` required (summary)

- Real **Vanna 2.x** stack: `Agent`, `ToolRegistry`, persistent memory, `UserResolver`, SQL via **`RunSqlTool`** / policy gate, OpenRouter-compatible LLM, FastAPI wiring.
- No “Vanna-inspired” substitute; inspect installed package APIs.
- Startup: profile → policies → Chroma memory → LLM → resolver → agent on `app.state.agent` (non-null when healthy).
- **`POST /chat`**: **`GuardedChatHandler`** → **`ChatHandler.handle_poll`** / **`handle_stream`** → **`Agent.send_message`** (no manual `LlmService.send_request` / `ToolRegistry.execute` in this route).
- Audit, rate limits, benchmarks, full docs (partially deferred below).

## What existed before this pass

- Custom sync `Agent` + internal `ToolRegistry` in `vai_app/agent_factory.py` (not Vanna).
- Bootstrap built that agent; no Vanna imports.
- No `/chat`; `GET /ready` lacked tool/LLM flags.

## Historical deviations (pre-Vanna-2.x path; resolved)

- Agent was not a `vanna.core.agent.Agent`; tools were not Vanna `Tool` / `ToolRegistry.execute`.
- Memory was project Chroma only, not Vanna `AgentMemory`.
- LLM path was httpx `OpenRouterChatService`, not Vanna `LlmService`.

## Fixes implemented

1. **`pyproject.toml`**: added `vanna>=2.0.2,<3`, `openai>=1.40,<2`; pytest ignores `PydanticDeprecatedSince20` emitted by Vanna’s vendored models.
2. **`vai_agent/vanna_integration/`**:
   - `factory.build_vanna_runtime` — **`run_sql`** + **`secure_run_sql`** `RunSqlTool` instances over **`PolicySqlRunner`**, with **`LocalFileSystem(working_directory=settings.vanna_file_storage_dir)`** for CSV exports.
   - `openrouter_llm.build_vanna_llm_service` — **`OpenAILlmService`** with `base_url` when OpenRouter configured; else **`MockLlmService`**.
   - Vanna tools wrapping existing explain/search logic; SQL execution only after `SqlPolicyEngine` / `PiiPolicyEngine` in `PolicySqlRunner`.
3. **`bootstrap.py`**: memory first, then `build_vanna_runtime`; stores **`VaiVannaRuntime`** on `app.state.agent`; readiness adds `tools_ready`, `llm_ready`; registers **`chat`** router.
4. **`api/query.py`**: async routes using Vanna `get_schemas` / `execute`.
5. **`api/chat.py`**: **`POST /chat`** → **`GuardedChatHandler`** (then Vanna agent stream).
6. **`bootstrap.py`**: **`register_chat_routes`** from **`vanna_fastapi_routes`** with **`GuardedChatHandler`**; removed **`app.state.llm_service`** — LLM only via **`runtime.vanna.llm_service`**.
7. **`api/health.py`**: `/ready` exposes `tools_ready`, `llm_ready`.
8. **`security/audit_log.py`**, **`security/prompt_injection.py`**: JSONL audit + lightweight injection heuristics.
9. **`api/rate_limit.py`**: user / IP / group / daily / concurrency limits for `/chat` and **`POST /agent/tools/.../invoke`**.
10. **`vanna_integration/factory.py`**: non-empty **`access_groups`** for SQL/schema/search tools from `security_policy`; registers **`SearchSavedCorrectToolUsesTool`**, **`SaveQuestionToolArgsTool`**, **`SaveTextMemoryTool`** from **`vanna.tools.agent_memory`**.
11. **`vanna_integration/vanna_audit.py`**: redacts SQL and secret-like keys before JSONL emit.
12. **`knowledge/profile_models.py`**: optional **`tool_access_groups`** map on **`SecurityPolicy`** for per-tool Vanna groups.
13. **`tests/`**: added `test_vanna_chat_endpoint`, `test_vanna_tool_access_groups`, `test_vanna_memory_tools`, `test_vanna_audit_redaction`, `test_rate_limiting`.

## Files touched (main)

- `pyproject.toml`
- `src/vai_agent/bootstrap.py`, `api/query.py`, `api/health.py`, `api/chat.py`, `api/rate_limit.py`
- `src/vai_agent/config/settings.py`, `memory/memory_factory.py`
- `src/vai_agent/security/audit_log.py`, `security/prompt_injection.py`
- `src/vai_agent/vanna_integration/*` (new package)
- `tests/test_api_query.py`, `test_bootstrap_startup.py`, `test_health.py`, `test_vanna_chat_endpoint.py`, `test_vanna_tool_access_groups.py`, `test_vanna_memory_tools.py`, `test_vanna_audit_redaction.py`, `test_rate_limiting.py`, `test_cleanup_contract.py`, `test_vanna_file_storage.py`, `test_no_legacy_runtime.py`, `test_vanna_routes_guarded.py`, `test_run_sql_tool_contract.py`

## Test status

- `uv run ruff check .` — clean.
- `uv run pytest` — **424 passed**.
- `scripts/validate_profile.py --profile dbnwind`, `scripts/benchmark_questions.py --profile dbnwind --source both --fail-on-error`, `scripts/seed_memory.py --profile dbnwind --force` — OK in verification.

## Remaining gaps (explicit)

- **Row filters / min_group_size / masking** in SQL engine: unchanged from prior project code; see `SECURITY.md` for policy surface.
- **Legacy sync `Agent` in `agent_factory.py`**: kept for existing unit tests (`test_agent.py`); production path is **`vanna_integration.factory`** / **`VaiVannaRuntime`**.
- **Packaging / delivery**: exclude `.git/`, caches, and local `.env` from shipped artifacts (`.gitignore` covers most; a release tarball should still omit `.git` explicitly).
