# SQL Assistant

A Vanna-powered SQL Assistant for safe, profile-driven querying of SQL Server
databases. Long-term goal: turn natural-language questions (Arabic / English)
into validated, audited, read-only `SELECT` statements over a known schema.

> Live phase status lives in [`PROGRESS.md`](./PROGRESS.md). The HTTP surface
> combines **Vanna 2.x** (`vanna.core.agent.Agent`, `ToolRegistry`, stock
> `ChatHandler`) with profile-driven SQL policy.

---

## Requirements

- Python **3.11+** (developed against 3.12)
- A local virtual environment at `.venv` inside the repo (mandatory — every
  command below assumes it)
- Windows / Linux / macOS

GNU `make` is optional; if you're on Windows without `make`, run the
equivalent commands listed under [Without `make`](#without-make).

---

## Quick start

```bash
# 1. Create + activate a local virtual environment
python -m venv .venv

# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# 2. Install runtime + dev dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# 3. Configure environment (DB + profile IDs are required for a green /ready)
cp .env.example .env          # then edit .env as needed

# 4. Run the test suite + linter
ruff check .
pytest

# 5. Start the FastAPI app (from repo root so profiles/ resolves)
uvicorn vai_agent.main:app --reload
```

### Endpoints you should recognise

Open <http://127.0.0.1:8000/health> — liveness probe (always `ok` if the process
is up):

```json
{ "status": "ok", "app": "sql-assistant", "version": "0.1.0", "env": "dev" }
```

Open <http://127.0.0.1:8000/ready> — readiness: profile load, DB-backed agent,
and Chroma memory must all initialise for `status: ok` without HTTP 503.

Interactive API docs: `/docs` and `/redoc` (automatically disabled when
`APP_ENV=prod`). Agent tooling: **`GET /agent/tools`**,
**`POST /agent/tools/{tool_name}/invoke`** (rate-limited; needs SQL Server).

**`POST /chat`** uses **`vanna.servers.base.ChatHandler.handle_poll`**, which
calls **`Agent.send_message`** (full Vanna agent loop — not manual
`llm_service.send_request` / `tool_registry.execute`).

Official Vanna HTTP endpoints are also registered:

- **`POST /api/vanna/v2/chat_poll`**
- **`POST /api/vanna/v2/chat_sse`**
- **`WS /api/vanna/v2/chat_websocket`**

Stock Vanna UI is served at **`GET /`** when routes are registered.

### Optional: OpenRouter (LLM)

Set `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and `OPENROUTER_MODEL` per
`.env.example`. With valid credentials an `OpenRouterChatService` is attached at
startup as **`request.app.state.llm_service`** and closed when the ASGI lifespan
ends. Omit or leave `LLM_PROVIDER=none` to skip outbound LLM calls.

---

## With `make`

```bash
make install   # install deps into .venv
make lint      # ruff check
make test      # pytest
make check     # lint + test (CI-equivalent)
make run       # uvicorn with reload
```

## Without `make`

All `make` targets resolve to direct calls against the `.venv` interpreter,
so any of the following work as drop-in replacements (PowerShell shown):

```powershell
.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\uvicorn.exe vai_agent.main:app --reload
```

---

## Project layout

```text
sql-assistant/
├── pyproject.toml
├── .env.example
├── Makefile
├── PROGRESS.md             # phased tracker
├── profiles/               # e.g. profiles/dbnwind/
├── scripts/                # CLI wrappers (validate_profile, benchmarks, ...)
├── docs/                   # ARCHITECTURE, COMPATIBILITY, operations, benchmarking
├── data/input/             # schema SQL snapshots for profiling
├── src/vai_agent/
│   ├── main.py             # uvicorn imports `app`
│   ├── bootstrap.py        # app factory + startup wiring + optional LLM client
│   ├── api/                # health (/health, /ready) + agent routes
│   ├── vai_app/            # Agent / ToolRegistry / context enhancer
│   ├── tools/              # SecureRunSql, ExplainSchema, ProfileSearch
│   ├── db/                  # ODBC connection + MSSQL runner + schema_extractor
│   ├── memory/              # Chroma persistent AgentMemory
│   ├── llm/                 # OpenRouter (OpenAI-compatible) chat completions
│   ├── knowledge/          # ProfileLoader / generators / benchmark
│   ├── security/
│   ├── users/
│   └── config/
└── tests/
```

---

## Profile CLI (high level)

```bash
python scripts/generate_profile_from_schema.py \
  --input data/input/schema.sql \
  --profile dbnwind

python scripts/validate_profile.py --profile dbnwind
python scripts/benchmark_questions.py --profile dbnwind    # requires real DB/schema
python scripts/seed_memory.py --profile dbnwind              # refreshes Chroma from profile
```

---

## Configuration

Primary keys mirror [`.env.example`](./.env.example):

| Variable            | Typical value      | Role                                      |
|--------------------|---------------------|--------------------------------------------|
| `APP_ENV`          | `dev`               | Enables `/docs`; use `prod` to lock down   |
| `DB_*`             | ODBC + SQL Server   | Required by agent tools + `/ready` checks  |
| `DB_PROFILE_ID`    | `dbnwind`           | Subdirectory under `PROFILES_ROOT`         |
| `CHROMA_PERSIST_DIR` | `.data/chroma`    | Persistent vector storage                  |
| `LLM_PROVIDER`     | `none` / `openrouter` | Attaches `app.state.llm_service`       |

See `.env.example` for the full annotated list (`USER_RESOLVER_MODE`,
`CONTEXT_MAX_TOKENS`, OpenRouter base URL/timeouts, etc.).

---

## Roadmap

See [`PROGRESS.md`](./PROGRESS.md) for the live status of each phase. The
master specification lives in `vai-prompt.txt`.
