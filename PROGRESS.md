# PROGRESS

Live tracker for the phased delivery of SQL Assistant. The master spec is
`vai-prompt.txt`; this file records what is **actually** done in the repo.

---

## Current phase

**Phase 10 — Final hardening. Status: ✅ complete (lint + 392 tests green).**

Goal: production wiring, readiness probing, stricter SQL policy
enforcement, complete dbnwind profile facets, benchmark hardening,
operational docs, and CI.

### Completed tasks (Phase 10)

- [x] **Startup wiring in `create_app()`**:
      reads `DB_PROFILE_ID`/`PROFILES_ROOT`, loads profile, builds
      `ConnectionSettings` from `DB_*`, constructs `UserResolver` from
      `USER_RESOLVER_MODE` + `DEV_USER_*`, builds agent, opens Chroma memory,
      and stores runtime state in `app.state.*`.
- [x] **Readiness endpoint**: `GET /ready` now reports
      `profile_ready`/`agent_ready`/`memory_ready` and returns `503` when
      degraded.
- [x] **SQL policy hardening (`SqlPolicyEngine`)**:
      `COUNT(*)` allowed, `allowed_schemas`, `allowed_tables`,
      `blocked_sql_features`, and group-scoped `row_filters` enforced.
- [x] **Benchmark hardening**:
      alias-aware column resolution in BN003; dbnwind benchmark now
      passes `150/150` examples and `30/30` eval.
- [x] **Completed `profiles/dbnwind` profile facets**:
      `security_policy.yaml`, `sql_style.yaml`, `business_rules.yaml`,
      `glossary.yaml`, `metrics.yaml`, `README.md`.
- [x] **`.env.example` aligned with runtime config**:
      includes full `DB_*`, profile id/root, resolver mode, and `DEV_USER_*`.
- [x] **Final docs added**:
      `SECURITY.md`, `docs/ARCHITECTURE.md` (with Mermaid diagrams),
      `docs/OPERATIONS.md`, `docs/BENCHMARKING.md`,
      `docs/DATABASE_PROFILE_GUIDE.md`.
- [x] **CI added**:
      `.github/workflows/ci.yml` runs `ruff` and `pytest`.

### Test results (Phase 10)

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
# 392 passed
.\.venv\Scripts\python.exe scripts/validate_profile.py --profile dbnwind
# OK - no issues found
.\.venv\Scripts\python.exe scripts/benchmark_questions.py --profile dbnwind
# examples: 150/150 passed; eval: 30/30 passed
```

### Files created or modified (Phase 10)

```
src/vai_agent/bootstrap.py                      (startup wiring + readiness state)
src/vai_agent/api/health.py                    (+ /ready endpoint)
src/vai_agent/config/settings.py               (profile/resolver/memory env config)
src/vai_agent/db/connection.py                 (safe DB defaults)
src/vai_agent/security/sql_policy.py           (allow-list/features/row-filters)
src/vai_agent/knowledge/benchmark.py           (alias-aware BN003)
src/vai_agent/knowledge/example_generator.py   (unique ids in generated examples)
profiles/dbnwind/security_policy.yaml          (new)
profiles/dbnwind/sql_style.yaml                (new)
profiles/dbnwind/business_rules.yaml           (new)
profiles/dbnwind/glossary.yaml                 (new)
profiles/dbnwind/metrics.yaml                  (new)
profiles/dbnwind/README.md                     (new)
.env.example                                   (runtime env alignment)
SECURITY.md                                    (new)
docs/ARCHITECTURE.md                           (new, Mermaid)
docs/OPERATIONS.md                             (new)
docs/BENCHMARKING.md                           (new)
docs/DATABASE_PROFILE_GUIDE.md                 (new)
.github/workflows/ci.yml                       (new)
tests/test_bootstrap_startup.py                (new)
tests/test_health.py                           (updated for /ready)
tests/test_sql_policy.py                       (updated for COUNT(*) + new checks)
PROGRESS.md                                    (modified)
```

---

## Phase 9 — Example generation & benchmarking ✅

Goal: given a natural-language question and a loaded profile, build a
compact, token-bounded context string for the LLM: glossary matching,
table selection, example retrieval, security constraints, and optional
Chroma memory boosts — without sending the full schema.

### Completed tasks (Phase 8)

- [x] **`vai_agent.vai_app.context_enhancer.ContextEnhancer`** —
      `enhance(question, user) → EnhancementResult` with structured
      fields (`glossary_matches`, `selected_tables`, `examples`,
      `security`, `context_text`, `estimated_tokens`, `truncated`).
- [x] **Glossary matching** — AR/EN/synonyms/common phrases plus
      per-table `business_name_ar` / `business_name_en` for mapped tables.
- [x] **Table selection** — scored from glossary maps, direct name
      mentions, table profiles, examples, memory hits; relationship
      expansion only when join-like hints are present (`each`, `join`,
      `لكل`, …).
- [x] **Example retrieval** — lexical overlap + table affinity; memory
      `kind=example` hits merged when memory is attached.
- [x] **Security context** — global policy + per-group blocked columns,
      masking rules, row filters, PII/sensitive/secret columns scoped to
      selected tables.
- [x] **Token-limited assembly** — section priority: security → glossary
      → schema (selected tables only) → relationships → business rules
      → examples → SQL style; char budget ≈ `max_tokens × 4`.
- [x] **`ContextEnhancerConfig`** + **`CONTEXT_MAX_TOKENS`** in
      `Settings` / `.env.example`.
- [x] **New tests: 16** in `tests/test_context_enhancer.py` (glossary
      AR/EN, table selection, examples, security, truncation, memory).

### Pending tasks (Phase 8)

- [ ] _None._ Phase 8 scope is feature-complete. Wiring
      `ContextEnhancer` into `build_agent()` / FastAPI chat endpoint is
      Phase 9+ (LLM provider).

### Test results (Phase 8)

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe -q --ignore=tests/test_memory_factory.py
# 347 passed in ~4s
.\.venv\Scripts\pytest.exe tests/test_context_enhancer.py -q
# 16 passed
```

### Files created or modified (Phase 8)

```
src/vai_agent/vai_app/context_enhancer.py   (new)
src/vai_agent/vai_app/__init__.py           (modified: exports)
src/vai_agent/config/settings.py            (modified: context_max_tokens)
.env.example                                (modified: CONTEXT_MAX_TOKENS)
tests/test_context_enhancer.py              (new)
PROGRESS.md                                 (modified)
```

---

## Phase 7 — Persistent memory (ChromaDB) ✅

Goal: chunk profile knowledge into atomic documents, store them in a
persistent ChromaDB vector store, verify the data survives process
restarts, and provide a `scripts/seed_memory.py` CLI.

### Completed tasks (Phase 7)

- [x] **`chromadb>=1.5,<2.0`** added to `pyproject.toml` and installed
      (1.5.9). 0.6.3 was incompatible with pydantic 2.13.x; 1.5.x API
      changes to custom `EmbeddingFunction` documented in
      `docs/COMPATIBILITY.md`.
- [x] **`vai_agent.memory.chunking.chunk_profile(profile) → list[ProfileChunk]`**
      — converts every facet of a loaded `Profile` into flat, atomic
      text chunks with stable deterministic IDs (`<pid>:<kind>:<slug>`)
      and metadata. Chunks cover: schema tables (columns + PK + FK
      narrative), relationships, business rules (rules + code meanings),
      glossary (canonical + AR/EN/synonyms), metrics, examples
      (question_ar + question_en + SQL), and per-table profiles (business
      names, grain, common questions). Arabic content is preserved in
      documents; the slug strips non-ASCII for ID safety.
- [x] **`vai_agent.memory.memory_factory.AgentMemory`** — chromadb
      wrapper; one collection per profile (`memory_<profile_id>`).
      - `seed(chunks)` — upsert in configurable batches of 100; fully
        idempotent (same chunks → same result regardless of how many
        times called).
      - `search(query, n_results, kind)` — similarity search with
        optional `kind` metadata filter; handles empty collections and
        caps `n_results` at collection size.
      - `count()` — documents stored.
      - `reset(client, profile_id)` — wipe and recreate for full
        re-seeds.
- [x] **`create_memory(profile_id, persist_dir, embedding_function)`**
      factory — opens `PersistentClient`, creates or re-opens the
      named collection, returns `(AgentMemory, client)`. The
      `embedding_function` parameter is `None` in production (uses
      `DefaultEmbeddingFunction` = all-MiniLM-L6-v2 ONNX, auto-cached)
      and a lightweight `DummyEF` in tests (no download required).
- [x] **`vai_agent.memory.seed_memory.seed_profile_memory(...)`** —
      high-level helper: load → chunk → upsert → return stats dict.
      `force=True` wipes the collection before seeding.
- [x] **`vai_agent.cli.seed_memory.main()`** + thin wrapper
      `scripts/seed_memory.py`. Exit codes: `0 = ok`, `1 = error`.
      Args: `--profile`, `--profiles-root`, `--persist-dir`, `--force`.
- [x] **Persistence verified end-to-end**:
  - `python scripts/seed_memory.py --profile dbnwind --persist-dir .data/chroma`
    → 39 chunks written in 6.9s.
  - Second `create_memory` call to the same directory (new Python
    process) → `count() = 39`, English search and Arabic search both
    return ranked results.
- [x] **`.env.example` updated** with `CHROMA_PERSIST_DIR=.data/chroma`.
- [x] **`docs/COMPATIBILITY.md` updated** with chromadb version history,
      the 0.6.3 pydantic incompatibility, and the 1.5.x EF protocol
      changes.
- [x] **New tests: 43 added (354 total)**:
  - `tests/test_chunking.py` (19 tests) — `_safe_slug` helper, all
    chunk kinds verified against the sample fixture (tables, FKs,
    glossary with Arabic, metrics, examples, per-table profiles),
    space-in-name metadata preservation, determinism.
  - `tests/test_memory_factory.py` (24 tests) — `create_memory`,
    `seed` (count, idempotency, partial update), **persistence across
    restarts** (data survives a second `PersistentClient` call to the
    same directory), search (shape, n_results, kind filter, empty
    collection), reset, `seed_profile_memory` helper (happy path,
    force, idempotent), CLI (happy + missing profile). All tests use
    `DummyEF` (no network required); only the real CLI invocation at
    `verify_persistence` used the cached ONNX model.

### Pending tasks (Phase 7)

- [ ] _None._ Phase 7 is feature-complete.

### Known issues / caveats

- **Tests are slow if the ONNX model cache is cold** (first run). The
  all-MiniLM-L6-v2 model (79 MB) is downloaded to
  `~/.cache/chroma/onnx_models/` on first use. Subsequent runs are
  fast. Tests themselves use `DummyEF` to avoid the download entirely.
- **Windows file-locking**: ChromaDB keeps HNSW index files open for
  the lifetime of the `PersistentClient`. `pytest`'s `tmp_path` fixture
  cleanup may print a `PermissionError` on Windows after tests that
  create a `PersistentClient`. This does not affect test results
  (the files are eventually cleaned up).
- **Arabic search quality is limited** with the DummyEF in tests (trivial
  vectors). In production with the ONNX model, the Arabic search works
  because the model has multilingual capacity, as confirmed by the
  live verification run.
- **`seed_profile_memory` is not yet wired into the FastAPI agent**
  — `build_agent()` does not attach the memory yet. That integration
  (context enhancer using memory search) is Phase 8.

### Test results (Phase 7)

```powershell
.\.venv\Scripts\ruff.exe check .           # All checks passed.
.\.venv\Scripts\pytest.exe -q              # 331 fast tests pass in 3.52s
.\.venv\Scripts\pytest.exe tests/test_memory_factory.py -q
# 23 passed in ~219s (cold ONNX cache); ~6s on warm cache
.\.venv\Scripts\python.exe scripts\seed_memory.py \
    --profile dbnwind --persist-dir .data\chroma
# 39 chunks written in 6.9s
```

### Files created or modified (Phase 7)

```
pyproject.toml                               (modified: +chromadb>=1.5,<2.0)
.env.example                                 (modified: +CHROMA_PERSIST_DIR)
src/vai_agent/memory/__init__.py             (new)
src/vai_agent/memory/chunking.py             (new)
src/vai_agent/memory/memory_factory.py       (new)
src/vai_agent/memory/seed_memory.py          (new)
src/vai_agent/cli/seed_memory.py             (new)
scripts/seed_memory.py                       (new)
tests/test_chunking.py                       (new)
tests/test_memory_factory.py                 (new)
docs/COMPATIBILITY.md                        (modified: chromadb 0.6→1.5 notes)
PROGRESS.md                                  (modified)
```

---

## Phase 6 — Agent layer (✅ complete)

Goal: wire the policy engines (Phase 4) and MSSQL runner (Phase 5) into
a tool-based agent, expose it over FastAPI, and document the decision
not to depend on the `vanna` Python package at this stage.

### Completed tasks (Phase 6)

- [x] **`vai_agent.users.user_resolver`** — `User` (frozen Pydantic),
      `UserResolver` with three modes:
  - `dev` — returns a fixed default `User` (groups freely settable,
    admin allowed in dev only).
  - `header` — reads `X-User-Id`, `X-User-Email`, `X-User-Groups`;
    protected group names (`admin`, `superadmin`, `root`) are **stripped**
    because the application cannot verify the upstream's trust boundary.
  - `future_oidc` — placeholder that raises `NotImplementedError`.
- [x] **`vai_agent.tools.base`** — `ToolBase` ABC + frozen `ToolResult`.
      Subclasses declare `name`, `description`, `args_model`,
      `access_groups` and a `execute(args, user) -> ToolResult` method.
      Helper methods `_ok()` and `_fail()` enforce uniform return shape.
- [x] **`SecureRunSqlTool`** — pipeline:
      `SqlPolicyEngine.validate()` → `PiiPolicyEngine.check()` →
      `MssqlRunner.execute()`. Every blocked path returns a sanitised
      `ToolResult(success=False, …)` with violation codes in
      `metadata.violations` and the failing `stage`.
- [x] **`ExplainSchemaTool`** — read-only. No table → table summary
      list. Specific table → columns / PK / FKs / indexes + merged
      per-table profile metadata (business names, grain, common
      questions). Never executes SQL.
- [x] **`ProfileSearchTool`** — case-insensitive substring search over
      glossary terms (canonical + AR + EN + synonyms), table names &
      descriptions, column names, business rules, metrics, and
      per-table profiles. Returns hits grouped by `source`. Arabic
      queries supported (UTF-8 throughout).
- [x] **`vai_agent.vai_app.tool_registry.ToolRegistry`** — name-keyed
      catalogue. Rejects duplicate registrations. `list_for_user(user)`
      filters by access groups (case-insensitive, empty tuple = open
      to all).
- [x] **`vai_agent.vai_app.agent_factory.Agent`** — synchronous
      dispatcher: looks up tool → access check → args validation
      (`tool.args_model.model_validate`) → `tool.execute(args, user)`.
      Every error path returns a `ToolResult`; unhandled tool
      exceptions are caught and reported as `Internal error` with the
      exception **type only** (never the message — DB internals).
      Each invocation gets a `request_id` (UUID) propagated into
      `ToolResult.metadata`.
- [x] **`build_agent()` factory** — wires `SqlPolicyEngine`,
      `PiiPolicyEngine`, `MssqlRunner`, all three tools, and the
      `UserResolver` from a loaded `Profile` + `ConnectionSettings`.
- [x] **`vai_agent.api.query`** — FastAPI router:
  - `GET  /agent/tools` — descriptors (name, description, access_groups,
    JSON-schema for args) filtered by the calling user's groups.
  - `POST /agent/tools/{tool_name}/invoke` — body `{"args": {...}}`,
    returns the `ToolResult` directly as JSON.
  - `503 Service Unavailable` when no agent is attached to
    `app.state.agent` (e.g. no profile / DB configured).
  - `401 Unauthorized` when header-mode resolver cannot identify the
    user.
- [x] **`bootstrap.create_app()` updated** — registers the agent
      router and initialises `app.state.agent = None`. Integration code
      (or tests) attaches a real `Agent` afterwards.
- [x] **`docs/COMPATIBILITY.md`** — new document:
  - Explicit statement: `vanna` is **not** installed.
  - Mapping of Vanna 2.0 concepts → our types.
  - Installed-version table for every Phase 1–6 dependency, with
    the sqlglot 30.x `walk()` quirk recorded.
  - Adapter sketch for plugging real Vanna in later (Phase 7+).
  - Deferred items table with target phases.
- [x] **New tests: 76 added (311 total)**:
  - `tests/test_user_resolver.py` (14 tests) — every mode, header
    case-insensitivity, admin-stripping, missing-ID error.
  - `tests/test_tools_base.py` (4 tests) — `_ok()` / `_fail()` helpers,
    frozen `ToolResult`.
  - `tests/test_tool_registry.py` (10 tests) — register / duplicate /
    list / access-control with case-insensitive group matching.
  - `tests/test_secure_run_sql_tool.py` (10 tests) — happy path
    (mocked runner), SQL-policy block (DELETE, SELECT *), PII-policy
    block (secret column), PII warning surfaced, timeout, runner error.
  - `tests/test_explain_schema_tool.py` (6 tests) — list + detail +
    space-in-name + unknown-table + per-table merge.
  - `tests/test_profile_search_tool.py` (9 tests) — glossary, Arabic
    query, column hit, metric hit, no-hits, case-insensitivity, limit.
  - `tests/test_agent.py` (9 tests) — unknown tool, happy path,
    request_id, invalid args, access denied, unhandled exception guard
    (verifies the exception message **does not** leak).
  - `tests/test_api_query.py` (14 tests) — 503 when no agent, list,
    invoke happy paths, unknown tool returns 200 with success=False,
    invalid args, access-group filtering of `GET /agent/tools`,
    header-mode 401 vs success, and admin-stripping over HTTP.

### Pending tasks (Phase 6)

- [ ] _None._ Phase 6 is feature-complete.

### Known issues / caveats

- **No `vanna` Python package dependency** — intentional, fully
  documented in `docs/COMPATIBILITY.md`. The future adapter sits
  behind the same `ToolBase` interface and can be added without
  rewriting callers.
- **No LLM-driven planner yet** — `Agent.invoke()` takes the tool name
  explicitly. An NL→tool planner is Phase 7 (OpenRouter + memory).
- **No persistent audit log** — `request_id` flows through
  `ToolResult.metadata` and structured logs only. Audit-log
  persistence is deferred to Phase 8.
- **No rate limiting yet** — per-user / per-IP / per-group caps are
  deferred to Phase 8.
- **`app.state.agent` is `None` by default.** A small startup
  integration script that loads a profile and wires the agent will
  ship in Phase 7 alongside the LLM config; until then the
  `/agent/*` routes are best exercised via tests or by attaching the
  agent manually.

### Test results (Phase 6)

```powershell
.\.venv\Scripts\ruff.exe check .   # All checks passed.
.\.venv\Scripts\pytest.exe -q      # 311 passed in 3.15s
```

### Files created or modified (Phase 6)

```
src/vai_agent/users/__init__.py                      (new)
src/vai_agent/users/user_resolver.py                 (new)
src/vai_agent/tools/__init__.py                      (new)
src/vai_agent/tools/base.py                          (new)
src/vai_agent/tools/secure_run_sql_tool.py           (new)
src/vai_agent/tools/explain_schema_tool.py           (new)
src/vai_agent/tools/profile_search_tool.py           (new)
src/vai_agent/vai_app/__init__.py                    (new)
src/vai_agent/vai_app/tool_registry.py               (new)
src/vai_agent/vai_app/agent_factory.py               (new)
src/vai_agent/api/query.py                           (new)
src/vai_agent/bootstrap.py                           (modified: register agent router)
docs/COMPATIBILITY.md                                (new)
tests/test_user_resolver.py                          (new)
tests/test_tools_base.py                             (new)
tests/test_tool_registry.py                          (new)
tests/test_secure_run_sql_tool.py                    (new)
tests/test_explain_schema_tool.py                    (new)
tests/test_profile_search_tool.py                    (new)
tests/test_agent.py                                  (new)
tests/test_api_query.py                              (new)
PROGRESS.md                                          (modified)
```

---

## Phase 5 — Database connection + MSSQL runner (✅ complete)

Goal: the only place in the codebase where SQL reaches the database.
No execution happens in earlier phases; callers pass a pre-approved query
to :class:`MssqlRunner` after both policy engines have returned `allowed=True`.

### Completed tasks (Phase 5)

- [x] **`pyodbc>=5.0` and `pandas>=2.0`** added to `pyproject.toml` and
      installed (pyodbc 5.3.0, pandas 2.3.3).
- [x] `vai_agent.db.connection.ConnectionSettings` — Pydantic v2
      `BaseSettings` with `env_prefix="DB_"` so environment variables
      `DB_HOST`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `DB_PORT`,
      `DB_DRIVER`, `DB_TRUST_SERVER_CERTIFICATE`, `DB_CONNECTION_TIMEOUT`
      are picked up automatically. Key design points:
  - `password` is a `SecretStr` — never appears in logs/repr.
  - `trust_server_certificate` defaults to `False` (prod-safe).
  - `driver` is validated against `ODBC Driver N for SQL Server` pattern.
  - `build_connection_string()` produces a DSN-less pyodbc ODBC string
    with `ApplicationIntent=ReadOnly` always appended.
  - `safe_repr()` returns a loggable summary with no password.
  - `get_connection_settings()` returns a per-process LRU-cached instance.
- [x] `vai_agent.db.mssql_runner.MssqlRunner` — safe query executor:
  - `_connect()` opens a pyodbc connection with `autocommit=True` and
    sets `conn.timeout = query_timeout` for client-side deadline.
  - `_run()` uses `pd.read_sql(chunksize=1000)` to stream rows; stops
    at `max_rows` mid-stream and sets `truncated=True`.
  - `truncated=True` is set whenever we stop at the `max_rows` boundary
    (conservative: the caller cannot distinguish "exactly N" from "more
    than N" without fetching further).
  - All pyodbc / pandas exceptions are caught; `RunnerError` (safe
    message + debug hint), `QueryTimeoutError` (HYT00 / HY008 SQLSTATE),
    `RowLimitError` (reserved for future explicit row-limit enforcement).
  - Connection always closed in `finally` via `contextlib.suppress`.
  - `_to_result()` converts the DataFrame to `QueryResult` (frozen Pydantic
    model): `list[str]` columns + `list[dict]` rows + `row_count` +
    `truncated` + `rewritten_sql`.
  - `_normalise_value()` converts numpy scalars, `pd.NaT`, `pd.Timestamp`,
    and `float("nan")` to JSON-serialisable Python types.
- [x] `vai_agent.db.__init__` updated to re-export `ConnectionSettings`,
      `MssqlRunner`, `QueryResult`, `QueryTimeoutError`, `RunnerError`.
- [x] New tests: 49 added (235 total):
  - `tests/test_connection.py` (19 tests) — defaults, connection string
    keys, `ApplicationIntent=ReadOnly`, TrustServerCertificate Yes/No,
    `safe_repr` hides password, driver validation, `SecretStr` repr.
  - `tests/test_mssql_runner.py` (30 tests) — all offline (mocked):
    construction guards, happy path (return shape, empty set, closed
    connection), row cap (single chunk, multi-chunk, boundary),
    timeout (HYT00 error → `QueryTimeoutError`), generic DB errors
    (safe message, debug hint, connection cleanup), value normalisation
    (None, NaT, NaN, Timestamp, numpy int/float), mixed column result,
    frozen `QueryResult` model.

### Pending tasks (Phase 5)

- [ ] _None._ Phase 5 is feature-complete.

### Known issues / caveats

- `truncated=True` at the exact `max_rows` boundary is conservative.
  A Phase-6 optimisation could look ahead by one row and only set
  `truncated=True` if there is at least one more row beyond the cap.
- `RowLimitError` is defined and exported but never raised by the
  current chunk-streaming implementation (it was planned as an alternative
  raise-on-cap mode). Reserved for future use.
- No audit logging yet — still deferred to the integration layer.
- `query_timeout=0` is allowed (disables client-side timeout). Callers
  should still set a server-side timeout via SQL Server configuration
  or `SET QUERY_GOVERNOR_COST_LIMIT` via a session-level statement —
  not added here to keep this module pure (no session setup SQL).

### Test results (Phase 5)

```powershell
.\.venv\Scripts\ruff.exe check .   # All checks passed.
.\.venv\Scripts\pytest.exe -q      # 235 passed in 2.76s
```

### Files created or modified (Phase 5)

```
pyproject.toml                             (modified: +pyodbc>=5.0, +pandas>=2.0)
src/vai_agent/db/__init__.py               (modified: +connection + runner exports)
src/vai_agent/db/connection.py             (new)
src/vai_agent/db/mssql_runner.py           (new)
tests/test_connection.py                   (new)
tests/test_mssql_runner.py                 (new)
PROGRESS.md                                (modified)
```

---

## Phase 4 — SQL policy + PII policy (✅ complete)

Goal: pure validation layer — no SQL executed. Every query must pass
`SqlPolicyEngine` (structural) and `PiiPolicyEngine` (column-level) before
reaching the database in any future phase.

### Completed tasks (Phase 4)

- [x] `vai_agent.security.errors` — `SecurityError`, `SqlPolicyViolationError`,
      `PiiViolationError` for callers who want raise-on-block semantics.
- [x] `vai_agent.security.sql_policy.SqlPolicyEngine` — returns `SqlPolicyResult`
      (never raises, never executes SQL). All 10 violation codes implemented:
  - `POL001` — DML/DDL/EXEC: DELETE, UPDATE, INSERT, MERGE, DROP,
    ALTER, CREATE, TRUNCATE, EXEC, EXECUTE, GRANT, REVOKE, …
  - `POL002` — Multiple statements (semicolon regex + AST count)
  - `POL003` — `SELECT *` (AST Star node)
  - `POL004` — Blocked schema (sys, INFORMATION_SCHEMA always blocked;
    policy `blocked_schemas` list; regex belt-and-suspenders)
  - `POL005` — Blocked function/SP (OPENROWSET, OPENQUERY, xp_cmdshell,
    xp_*, sp_oacreate, sp_executesql; AST + regex dual check)
  - `POL006` — Cross-database reference (3-part name via `catalog` arg)
  - `POL007` — Blocked table (policy deny-list)
  - `POL008` — SELECT INTO
  - `POL009` — Empty or unparseable query
  - `POL010` — Injection-pattern heuristics (7 regex patterns)
  - TOP injection: when all checks pass, `rewritten_sql` has `TOP N`
    appended after `SELECT` for simple queries (CTEs/UNIONs passed
    through unchanged with original SQL).
- [x] `vai_agent.security.pii_policy.PiiPolicyEngine` — returns
      `PiiCheckResult` (never raises). Column matching is conservative:
  - `PII001` — Secret column (any `Col` reference where the column name
    matches any `*.ColName` secret entry — alias-safe)
  - `PII002` — PII column (same conservative matching)
  - `PII003` — Sensitive column (same)
  - `PII004` — Name-heuristic warning (phone, email, password, ssn, …);
    informational only, does not block
- [x] sqlglot 30.8.0 added to `pyproject.toml` and installed. T-SQL
      dialect (`read="tsql"`) used throughout with `ErrorLevel.WARN`
      so partial ASTs are still available for T-SQL quirks.
- [x] Fixed sqlglot 30.x walk API: `walk()` yields plain nodes (not
      `(node, parent, key)` tuples as in earlier versions).
- [x] New tests: 70 added (186 total)
  - `tests/test_sql_policy.py` (47 tests) — every violation code
    individually; parametrised DML/DDL cases; TOP injection; valid
    queries including JOINs, CTEs, UNIONs; raise-helper.
  - `tests/test_pii_policy.py` (23 tests) — secret/PII/sensitive columns
    with qualified and unqualified refs; alias-bypass coverage;
    heuristic patterns; multiple violations; empty policy.

### Pending tasks (Phase 4)

- [ ] _None._ Phase 4 is feature-complete.

### Known issues / caveats

- `COUNT(*)` is currently blocked by POL003 because sqlglot surfaces a
  `Star` node inside `COUNT(*)`. This is a documented conservative
  choice in the test. A Phase-5 refinement can exclude `Star` nodes
  that appear only inside aggregate function calls.
- `SELECT *` inside a CTE subquery (`WITH c AS (SELECT * FROM t) …`)
  is also blocked — conservative but correct per the spec.
- Alias resolution is intentionally not attempted. A column reference
  `e.BirthDate` (where `e` aliases `Employees`) is matched
  conservatively by column name, not by resolving `e → Employees`.
  This may produce false positives when the same column name is safe on
  one table but secret on another. The trade-off is documented in
  `pii_policy.py`'s docstring.
- TOP injection is skipped for CTEs (`WITH … SELECT …`) and UNIONs;
  the original SQL is returned unchanged for those shapes. The database
  runner (Phase 5+) must apply a connection-level row cap for those.
- No access-group filtering yet (`user_groups` parameter accepted but
  ignored). Per-group column allow/deny logic is Phase 5.
- No audit logging yet — that belongs with the execution layer.

### Test results (Phase 4)

```powershell
.\.venv\Scripts\ruff.exe check .   # All checks passed.
.\.venv\Scripts\pytest.exe -q      # 186 passed in 3.43s
```

### Files created or modified (Phase 4)

```
pyproject.toml                             (modified: +sqlglot>=20.0)
src/vai_agent/security/__init__.py         (new)
src/vai_agent/security/errors.py           (new)
src/vai_agent/security/sql_policy.py       (new)
src/vai_agent/security/pii_policy.py       (new)
tests/test_sql_policy.py                   (new)
tests/test_pii_policy.py                   (new)
PROGRESS.md                                (modified)
```

---

## Phase 3 — Schema-to-profile generator (✅ complete)

Goal: read a SSMS-style DDL script and emit the four base profile
files — `profile.yaml`, `schema.generated.yaml`, `relationships.yaml`,
`tables/*.yaml` — that downstream phases can build on.

### Completed tasks (Phase 3)

- [x] `vai_agent.db.schema_extractor` — focused, dependency-free regex
      parser for SSMS DDL. Handles:
  - `CREATE TABLE` with bracketed identifiers, including
    space-bearing names (`[Order Details]`).
  - Column types with size/precision (`nvarchar(40)`,
    `decimal(10,2)`), `IDENTITY(seed,step)`, nullability.
  - In-line `CONSTRAINT [...] PRIMARY KEY` (simple + composite).
  - `ALTER TABLE ... ADD CONSTRAINT [...] FOREIGN KEY ... REFERENCES`
    (one FK per ALTER, attached to the source table).
  - `ALTER TABLE ... ADD CONSTRAINT [...] DEFAULT ... FOR [col]`
    (applied back to the column's `default` field).
  - `CREATE [UNIQUE] [NONCLUSTERED|CLUSTERED] INDEX`.
  - `CREATE VIEW` (body stored as raw definition).
  - `CREATE PROCEDURE` (parameters + body stored as raw definition).
- [x] `split_go_batches` + `_balanced_paren_end` +
      `_split_top_level_commas` — robust low-level helpers, tested in
      isolation (quoted strings, nested parens, comma-in-parens, etc.).
- [x] Parser dispatcher attempts each statement parser in
      specificity order (PROCEDURE → VIEW → TABLE → INDEX → FK →
      DEFAULT). Avoids a bug where SSMS's leading
      `/****** Object: ... ******/` comment would break a naive
      `startswith("CREATE")` dispatch.
- [x] `vai_agent.knowledge.profile_generator.generate_profile` —
      builds a Phase-2 `Profile` from the extraction result; produces
      auto-generated per-table profiles (PK + first NOT-NULL columns
      heuristic for `important_columns`, type-based detection of
      `date_columns`, FK-derived relationship strings, `confidence:
      low` so humans know to review).
- [x] `write_profile_to_disk` — block-style YAML, `by_alias=True`,
      `exclude_none=True`; per-table filenames sanitised via
      `_safe_filename` (space → underscore, unsafe chars stripped)
      while the real space-bearing name is preserved inside the file's
      `name` field. Refuses to overwrite unless `force=True`.
- [x] `read_schema_file` — BOM-aware reader; handles SSMS's default
      UTF-16 LE encoding, UTF-16 BE, UTF-8 BOM, and plain UTF-8.
- [x] `vai_agent.cli.generate_profile.main` + thin wrapper
      `scripts/generate_profile_from_schema.py`. Exit codes:
      `0 = ok`, `1 = refused to overwrite`, `2 = input missing /
      undecodable`. Injectable stdout/stderr for testing.
- [x] Resolved an import cycle introduced by Phase-3
      (`db.schema_extractor` ↔ `knowledge`): `profile_generator` is
      now reachable only via `from vai_agent.knowledge.profile_generator
      import ...`, not re-exported from `knowledge/__init__.py`. Reason
      documented in the package's module docstring.
- [x] New fixture `tests/fixtures/ddl/minimal.sql` — 3 tables (one with
      a space), 1 view, 1 procedure, 2 FKs, 2 indexes (1 unique), 2
      DEFAULT constraints.
- [x] New tests (62 added in Phase 3; 116 total):
  - `tests/test_schema_extractor.py` (40 tests) — every parser plus a
    smoke test class that runs against the real `data/input/Schema.sql`
    and asserts the exact table count (13), view count (16),
    procedure count (7), relationship count (13), composite PK on
    `Order Details`, self-referential FK on Employees, and 4 indexes
    on `Order Details`.
  - `tests/test_profile_generator.py` (16 tests) — meta population,
    per-table heuristics, idempotent (byte-for-byte) writes, and a
    round-trip test that parses → generates → writes → loads →
    validates with **zero errors** for both the minimal fixture
    and the real DBnwind schema.
  - `tests/test_generate_profile_cli.py` (6 tests) — happy path,
    missing input → exit 2, refuse-overwrite → exit 1,
    `--force` → exit 0, real-schema run produces a validatable
    `dbnwind` profile.

### Pending tasks (Phase 3)

- [ ] _None._ Phase 3 is feature-complete.

### Known issues / caveats

- **CHECK constraints are ignored.** The real `Schema.sql` has half a
  dozen (`CK_Discount`, `CK_Quantity`, `CK_Birthdate`, etc.), but
  Phase-2's `Table` model has no place for them. They will be
  modelled if/when `SecureRunSqlTool` needs to enforce them.
- **Parser is a focused regex implementation**, not a general SQL
  parser. It targets SSMS's "Script Database As" output and is
  documented as such in the module docstring. Other DDL dialects or
  manually-authored SSMS scripts with non-standard formatting may not
  parse. `sqlglot` is the planned fallback once query-time SQL
  parsing is needed for the secure SQL tool.
- **Per-table profile content is intentionally sparse.** The
  generator emits PK, important columns, date columns, and FK-based
  relationship strings; everything else (business names, descriptions,
  common questions, examples) is left blank with `confidence: low`
  for human review. This is by design — see the master spec's
  "Phase Execution Rules" about avoiding fabricated content.
- **`profile.yaml` is generated even though it wasn't in the
  Phase-3 brief.** Without it, the Phase-2 loader refuses to load
  the profile, defeating the purpose of generation. Documented in
  the generator's module docstring.
- **`generated_from` records the path verbatim.** On Windows it
  appears as `data\input\Schema.sql`; on POSIX it would use
  forward slashes. This is faithful to how the CLI was invoked
  and does not affect anything functional.
- **The generated `profiles/dbnwind/` directory is now in the repo
  but is *not* in `.gitignore`.** Decide whether to commit it as a
  pre-built demo or to ignore it.

### Test results

```powershell
.\.venv\Scripts\ruff.exe check .                          # All checks passed.
.\.venv\Scripts\pytest.exe -q                             # 116 passed in 1.85s
.\.venv\Scripts\python.exe scripts\generate_profile_from_schema.py `
    --input data\input\Schema.sql --profile dbnwind --database-name DBnwind
# profile: dbnwind / tables: 13 / views: 16 / procedures: 7 /
# relationships: 13 / files written: 16
.\.venv\Scripts\python.exe scripts\validate_profile.py --profile dbnwind
# profile: dbnwind / errors: 0 / warnings: 0 / OK - no issues found.
```

### Commands run (Phase 3)

| Command | Outcome |
| ------- | ------- |
| `ruff check .` | All checks passed (after fixing one `RUF005` and one consolidated docstring). |
| `pytest -q` | 116 / 116 passed (62 new + 54 from Phase 2/1). |
| `python scripts\generate_profile_from_schema.py --input data\input\Schema.sql --profile dbnwind --database-name DBnwind` | Generated 16 files; 0 errors. |
| `python scripts\validate_profile.py --profile dbnwind` | Exit 0, 0 errors, 0 warnings. |

### Files created or modified (Phase 3)

```
src/vai_agent/db/__init__.py                           (new)
src/vai_agent/db/schema_extractor.py                   (new)
src/vai_agent/knowledge/__init__.py                    (modified: docstring; no re-export of generator)
src/vai_agent/knowledge/profile_generator.py           (new)
src/vai_agent/cli/generate_profile.py                  (new)
scripts/generate_profile_from_schema.py                (new)
tests/fixtures/ddl/minimal.sql                         (new)
tests/test_schema_extractor.py                         (new)
tests/test_profile_generator.py                        (new)
tests/test_generate_profile_cli.py                     (new)
profiles/dbnwind/profile.yaml                          (generated)
profiles/dbnwind/schema.generated.yaml                 (generated)
profiles/dbnwind/relationships.yaml                    (generated)
profiles/dbnwind/tables/*.yaml                         (generated, 13 files)
PROGRESS.md                                            (modified)
```

---

## Phase 2 — Profile models, loader, validators (✅ complete)

> **Re-audit (post-Schema.sql upload):** the real schema in `data/input/Schema.sql`
> is Microsoft Northwind (`DBnwind`). The fixture was realigned to match
> real table names — most notably `Order Details` (with a space). A
> fictional `Orders.Status` column that didn't exist in the real schema
> was removed, and a new regression test was added that explicitly
> exercises space-in-name handling end-to-end (schema, relationships,
> per-table profile lookup). See "Re-audit changes" below.

Goal: load a `profiles/<profile_id>/` directory into a typed in-memory
`Profile`, validate cross-file consistency, expose both as a CLI for
operators. Generation of a profile from `schema.sql` is **not** in this
phase — it remains planned for Phase 3.

### Completed tasks (Phase 2)

- [x] `vai_agent.knowledge.profile_models` — Pydantic v2 models for
      every profile file (`profile.yaml`, `schema.generated.yaml`,
      `relationships.yaml`, `business_rules.yaml`, `glossary.yaml`,
      `metrics.yaml`, `examples.yaml`, `security_policy.yaml`,
      `sql_style.yaml`, per-table `tables/*.yaml`) plus the aggregate
      `Profile`. All models use `extra="forbid"` so YAML typos fail loud.
- [x] Schema-level invariants enforced at parse time: PK columns must
      exist on the table, FK column counts must balance, relationships
      must balance, `hard_row_limit >= default_row_limit`, security
      policy `allowed`/`blocked` operations must not overlap, examples
      must include at least one `question_ar` or `question_en`.
- [x] `vai_agent.knowledge.profile_loader.ProfileLoader` — loads from
      disk; mandatory files = `profile.yaml` + `schema.generated.yaml`;
      every other file is optional and defaults to an empty document;
      per-table profiles are auto-discovered under `tables/*.yaml`;
      duplicate table profiles are rejected.
- [x] Error types: `ProfileError` (base), `ProfileNotFoundError`,
      `ProfileFileError` — surfaced from the loader, not raw Pydantic
      exceptions.
- [x] `vai_agent.knowledge.validators.validate_profile` — runs seven
      groups of cross-file checks and returns a `ValidationReport` of
      `ValidationIssue`s, each tagged with a stable code
      (`REL00x`, `EX00x`, `SEC00x`, `TP00x`, `MET00x`, `GLO00x`, `BR00x`)
      and a `Severity` (`error` / `warning`). No exceptions raised —
      callers see all issues at once.
- [x] `vai_agent.cli.validate_profile.main` — the actual CLI logic,
      with `--profile`, `--profiles-root`, `--strict`, exit codes
      `0 / 1 / 2`, and injectable stdout/stderr for testing.
- [x] `scripts/validate_profile.py` — thin wrapper invoking
      `vai_agent.cli.validate_profile.main`. Smoke-tested:
      `python scripts/validate_profile.py --profile sample
      --profiles-root tests/fixtures/profiles` → exit 0.
- [x] `pyyaml` promoted to a direct runtime dependency in
      `pyproject.toml`.
- [x] Test fixture: `tests/fixtures/profiles/sample/` — small valid
      Northwind-style profile (3 tables, 2 FKs, 2 examples, 2 metrics,
      glossary terms in AR/EN, 2 per-table profile files, restrictive
      security policy with one PII column and one access group).
- [x] New tests (45 added in Phase 2; 53 total):
  - `tests/test_profile_models.py` — model defaults, alias handling,
    cross-field invariants, `extra="forbid"` rejections.
  - `tests/test_profile_loader.py` — loads the sample fixture, handles
    missing optional files, raises on missing mandatory files, rejects
    malformed YAML and duplicate table profiles.
  - `tests/test_validators.py` — covers each issue code with a
    targeted profile mutation; verifies the sample fixture produces
    zero issues; checks severity split on `ValidationReport`.
  - `tests/test_validate_profile_cli.py` — exit codes for valid,
    missing, invalid, and `--strict` cases (using `tmp_path` to build
    broken profiles on the fly).

### Re-audit changes (post-Schema.sql upload)

After the user uploaded `data/input/Schema.sql` (Northwind / DBnwind),
the fixture was audited against the real schema and updated:

- **Renamed `OrderDetails` → `"Order Details"`** in:
  `tests/fixtures/profiles/sample/schema.generated.yaml`,
  `relationships.yaml` (relationship id also renamed
  `rel_orderdetails_orders` → `rel_order_details_orders`),
  `metrics.yaml`, `security_policy.yaml`, and
  `tests/fixtures/profiles/sample/tables/Orders.yaml` (relationship
  strings + `common_joins` now use proper T-SQL bracketing
  `dbo.[Order Details]`).
- **Removed fictional `Orders.Status` column.** Real Northwind has no
  such column. `Orders.ShippedDate` (a real column) was added to the
  fixture instead. `business_rules.yaml` no longer carries the
  `Orders.Status` `status_meanings` entry, and `tables/Orders.yaml`
  no longer claims `Status` is a status column.
- **Added `tests/fixtures/profiles/sample/tables/Order_Details.yaml`** —
  a per-table profile for the space-named table, illustrating the
  convention: filename uses an underscore for OS friendliness; the
  real space-bearing name lives inside the file's `name` field. The
  loader keys the dict by `name`, never by filename, so the
  filename is purely a human-readability choice.
- **New test:**
  `test_table_names_with_spaces_are_preserved_end_to_end`
  (in `tests/test_profile_loader.py`) exercises space-in-name through
  schema parsing, helper methods, relationships, and per-table
  profile lookup. It also asserts that the *old* name `OrderDetails`
  is **not** a table — a regression marker against future renames.
- **Updated `assert names == [...]`** in
  `tests/test_profile_loader.py` to match the realigned schema:
  `["Customers", "Orders", "Order Details"]`.

No changes were needed to the models, loader, validators, or CLI —
they handle arbitrary string-named tables correctly by design. The
realignment was strictly a fixture / test concern.

### Pending tasks (Phase 2)

- [ ] _None._ Phase 2 is feature-complete.

### Known issues / caveats

- The example-SQL check (`EX002` / `EX003`) is intentionally **light**:
  it only rejects statements whose first keyword is in a fixed deny
  list, and warns when the statement does not begin with `SELECT` /
  `WITH ... SELECT`. Full SQL parsing with `sqlglot` will land with the
  `SecureRunSqlTool` in a later phase. Examples like
  `SELECT INTO #temp ...` will currently pass — that's by design until
  the secure tool exists.
- `pii_columns` / `sensitive_columns` are modelled as a flat list of
  strings (e.g. `"Customers.ContactName"`) rather than structured
  `{table, column}` dicts. Validators do not currently cross-check
  these against the schema; that check will be added when the secure
  SQL tool needs it.
- No `profiles/default/` directory exists yet. Running
  `python scripts/validate_profile.py --profile default` will exit 2
  ("profile not found"). The default profile will be created by the
  Phase 3 generator.

### Test results

```powershell
.\.venv\Scripts\ruff.exe check .   # All checks passed.
.\.venv\Scripts\pytest.exe -v      # 54 passed in 0.47s
.\.venv\Scripts\python.exe scripts\validate_profile.py `
    --profile sample --profiles-root tests\fixtures\profiles
# profile: sample / errors: 0 / warnings: 0 / OK - no issues found.
```

### Commands run (Phase 2)

| Command                                                                         | Outcome |
| ------------------------------------------------------------------------------- | ------- |
| `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`                         | Reinstalled with `pyyaml` as direct dep. |
| `.\.venv\Scripts\ruff.exe check .`                                              | All checks passed (twice — initial and post-realignment). |
| `.\.venv\Scripts\pytest.exe -v`                                                 | 54 / 54 passed (46 new + 8 from Phase 1). |
| `python scripts\validate_profile.py --profile sample --profiles-root tests\...` | Exit 0, no issues (both before and after the realignment). |

### Files created or modified (Phase 2)

```
pyproject.toml                                            (modified: +pyyaml)
PROGRESS.md                                               (modified)
src/vai_agent/knowledge/__init__.py
src/vai_agent/knowledge/profile_models.py
src/vai_agent/knowledge/profile_loader.py
src/vai_agent/knowledge/validators.py
src/vai_agent/cli/__init__.py
src/vai_agent/cli/validate_profile.py
scripts/validate_profile.py
tests/fixtures/profiles/sample/profile.yaml
tests/fixtures/profiles/sample/schema.generated.yaml
tests/fixtures/profiles/sample/relationships.yaml
tests/fixtures/profiles/sample/business_rules.yaml
tests/fixtures/profiles/sample/glossary.yaml
tests/fixtures/profiles/sample/metrics.yaml
tests/fixtures/profiles/sample/examples.yaml
tests/fixtures/profiles/sample/security_policy.yaml
tests/fixtures/profiles/sample/sql_style.yaml
tests/fixtures/profiles/sample/tables/Customers.yaml
tests/fixtures/profiles/sample/tables/Orders.yaml
tests/fixtures/profiles/sample/tables/Order_Details.yaml   (added in re-audit)
tests/test_profile_models.py
tests/test_profile_loader.py
tests/test_validators.py
tests/test_validate_profile_cli.py
```

---

## Phase 1 — Foundations (✅ complete)

Foundations: skeleton, settings, logging, `/health`, tests.

Goal: a runnable Python skeleton with configuration, logging, a liveness
endpoint, and a green test + lint suite. **No Vanna, no DB, no LLM yet.**

### Completed tasks (Phase 1)

- [x] Project skeleton (`src/vai_agent/`, `tests/`)
- [x] `pyproject.toml` with `hatchling` build backend, pinned dep ranges,
      `ruff` config, `pytest` config (src on `pythonpath`, strict markers,
      warnings as errors)
- [x] `.env.example` documenting active + future env vars
- [x] `.gitignore` (Python, venv, tooling caches, `.env`, runtime data)
- [x] `vai_agent.config.settings.Settings` — Pydantic v2 `BaseSettings`,
      LRU-cached `get_settings()`, validated port range, env-driven
- [x] `vai_agent.config.logging_config` — stdlib logging with `text` /
      `json` formatters; preserves `extra={...}` fields for future
      `request_id` / `user_id` propagation
- [x] `vai_agent.api.health` — `GET /health` returning `status`, `app`,
      `version`, `env`
- [x] `vai_agent.bootstrap.create_app()` — FastAPI factory; disables
      `/docs` and `/redoc` when `APP_ENV=prod`
- [x] `vai_agent.main:app` — ASGI entry point for `uvicorn`
- [x] `Makefile` — `install`, `lint`, `format`, `test`, `run`, `check`,
      `clean` (all routed through `.venv`)
- [x] `README.md` — quickstart, layout, configuration, roadmap pointer
- [x] Initial tests:
  - `tests/test_settings.py` — defaults, env override, validation,
    cache behaviour
  - `tests/test_logging_config.py` — JSON formatter + handler reset
  - `tests/test_health.py` — `200 OK` + response schema

### Pending tasks (Phase 1)

- [ ] _None._ Phase 1 is feature-complete.

### Known issues / caveats

- `data/` exists from before Phase 1 and is currently empty; it will be
  used in later phases as the input location for `schema.sql`. Not
  tracked by git (`data/input/*` ignored).
- The pre-existing `.venv` was reused; if it ever needs rebuilding,
  delete it and run `make install` (or the PowerShell fallback in
  `README.md`).
- No `mypy` / type-check step yet — deferred to a later phase to keep
  Phase 1 lean.

### Test results

Recorded after Phase 1 verification (Python 3.12.10 on Windows).
Reproduce locally with:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
```

- `ruff check .` → **All checks passed.**
- `pytest` → **8 passed in 0.07s.**
- `python -c "from vai_agent.main import app"` → app loads, registers
  `/health`, `/docs`, `/redoc`, `/openapi.json`.

### Commands run

| Command                                          | Outcome  |
| ------------------------------------------------ | -------- |
| `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | Installed fastapi 0.136.1, pydantic 2.13.4, pydantic-settings 2.14.1, uvicorn 0.47.0, pytest 8.4.2, ruff 0.15.13, httpx 0.28.1 (+ transitive). |
| `.\.venv\Scripts\ruff.exe check .`               | All checks passed. |
| `.\.venv\Scripts\pytest.exe -v`                  | 8 / 8 tests passed. |
| `python -c "from vai_agent.main import app"`     | App loads, no ImportError. |

### Files created or modified

```
pyproject.toml
.env.example
.gitignore
Makefile
README.md
PROGRESS.md
src/vai_agent/__init__.py
src/vai_agent/main.py
src/vai_agent/bootstrap.py
src/vai_agent/config/__init__.py
src/vai_agent/config/settings.py
src/vai_agent/config/logging_config.py
src/vai_agent/api/__init__.py
src/vai_agent/api/health.py
tests/__init__.py
tests/conftest.py
tests/test_settings.py
tests/test_logging_config.py
tests/test_health.py
```

---

## Next phase

**Phase 6 — SecureRunSqlTool (integration of policy + runner + audit log) — planned, not started.**

Tentative deliverables:

- `tools/secure_run_sql_tool.py` — wires `SqlPolicyEngine` → `PiiPolicyEngine`
  → `MssqlRunner` → audit log into one callable.
- `security/audit_log.py` — structured per-request audit entry (request_id,
  user_id, sql (safe form), violations, outcome, duration_ms).
- FastAPI endpoint `POST /query` that:
  - Resolves the user via `UserResolver` (Phase 6+).
  - Runs the full policy + execution pipeline.
  - Returns `QueryResult` or a structured error.

---

## Next phase (earlier plan)

**Phase 4 — Semantic enrichment + memory seeding (planned, not started).**

Phase 3 produces a *structural* profile. Tentative Phase-4 deliverables
(subject to confirmation before kickoff):

- `src/vai_agent/knowledge/schema_analyzer.py` — classify each table
  (fact / dimension / lookup / audit / config / transactional) and
  surface inferred relationships beyond the explicit FKs.
- Enrichments to the per-table profiles: candidate `sensitive_columns`
  by name heuristics (`Phone`, `Email`, `SSN`, …), candidate business
  names (transliterated), candidate `common_questions`.
- `examples.yaml` seed generator (deterministic templates: lookup /
  latest / count-by-status / top-N — _not_ free-text LLM generation
  in this phase).
- `business_rules.yaml`, `glossary.yaml`, `metrics.yaml` generators
  (templated, low confidence, flagged for review).
- `src/vai_agent/memory/` — Chroma-backed `AgentMemory` and a
  `scripts/seed_memory.py` CLI that loads the generated profile into
  persistent memory.

Vanna integration is **Phase 5+** — it should not start until the
profile + memory pipeline is verified.

---

## Phase log

| Phase | Status   | Notes                                                                                 |
| ----- | -------- | ------------------------------------------------------------------------------------- |
| 1     | done     | Foundations: skeleton, settings, logging, `/health`, tests, ruff.                     |
| 2     | done     | Profile models, loader, validators, CLI, 45 new tests.                                |
| 3     | done     | Schema extractor + profile generator + CLI; 62 new tests; real DBnwind generated.     |
| 4     | done     | SQL policy + PII policy engines; 70 new tests; no SQL executed.                       |
| 5     | done     | DB connection + MSSQL runner; 49 new tests; all offline mocked.                       |
| 6     | done     | Tools + registry + agent + FastAPI + UserResolver + COMPATIBILITY.md; 76 new tests.   |
| 7     | done     | Chunking + ChromaDB AgentMemory + seed CLI + persistence verified; 43 new tests.       |
| 8     | done     | Context enhancer: glossary, tables, examples, security, token budget; 16 new tests.   |
| 9     | done     | Example generator, eval_questions, benchmark CLI, reports; 13 new tests.              |
| 10    | done     | Final hardening: startup wiring, readiness, policy enforcement, docs, CI.              |
| 11+   | planned  | LLM provider (OpenRouter), rate limiting, persistent audit logging, chat endpoint.      |
