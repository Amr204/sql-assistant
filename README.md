# SQL Assistant

A Vanna-powered SQL Assistant for safe, profile-driven querying of SQL Server
databases. Long-term goal: turn natural-language questions (Arabic / English)
into validated, audited, read-only `SELECT` statements over a known schema.

> Architecture and documentation standards: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md),
> [`docs/CODE_DOCUMENTATION.md`](./docs/CODE_DOCUMENTATION.md).

> Live phase status lives in [`PROGRESS.md`](./PROGRESS.md). The HTTP surface
> combines **Vanna 2.x** (`vanna.core.agent.Agent`, `ToolRegistry`,
> `ChatHandler` / `GuardedChatHandler`) with profile-driven SQL policy and a
> first-party web UI on **`/app`**.

---

## Requirements

- Python **3.11+** (developed against 3.12)
- A local virtual environment at `.venv` inside the repo (mandatory — every
  command below assumes it)
- Windows / Linux / macOS
- **Microsoft ODBC Driver for SQL Server** (17 or 18) on the host where the app
  runs — required whenever agent tools or startup wiring touch the database
  (matches `DB_DRIVER` in `.env`)
- A reachable **Microsoft SQL Server** database whose schema matches the active
  profile (the bundled `dbnwind` profile expects a Northwind-style database;
  align `DB_DATABASE` with your instance)

GNU `make` is optional; if you're on Windows without `make`, run the
equivalent commands listed under [Without `make`](#without-make).

---

## Quick start

This walkthrough takes you from a clean checkout to a running HTTP API and
lists everything you must supply for **`GET /ready` to return `status: ok`**
(no HTTP 503). Run all commands from the **repository root** so `profiles/`,
`.env`, and relative paths such as `CHROMA_PERSIST_DIR` resolve correctly.

### Prerequisites checklist

| Item | Purpose |
|------|---------|
| Python 3.11+ | Runtime and tooling |
| Git checkout at repo root | `profiles/`, `pyproject.toml`, `.env` resolution |
| Virtualenv at `.venv` | Isolated dependencies (assumed below) |
| ODBC Driver 17/18 for SQL Server | `pyodbc` connection string in `DB_DRIVER` |
| SQL Server TCP endpoint + DB | Vanna agent + tools; startup builds a read-only ODBC connection (`ApplicationIntent=ReadOnly`) |
| Editable `.env` from [`.env.example`](./.env.example) | App + `DB_*` settings |

### What you must configure (data and secrets)

1. **Database (`DB_*` in `.env`)** — Host, port, database name, SQL login, and
   password. Use a **read-only** SQL user in production. `DB_DRIVER` must match an
   installed ODBC driver name (for example `ODBC Driver 18 for SQL Server`).
   Set `DB_TRUST_SERVER_CERTIFICATE=true` only for dev when using self-signed
   TLS on SQL Server; keep `false` in production.
2. **Profile id (`DB_PROFILE_ID`)** — Must name a subdirectory under
   `PROFILES_ROOT` (default `profiles/`). The repo ships **`dbnwind`**; your
   database schema and table/column names should match what that profile
   describes (or generate a new profile — see [Profile CLI](#profile-cli-high-level)).
3. **Chroma (`CHROMA_PERSIST_DIR`)** — Defaults to `.data/chroma`; the directory
   is created on first run. No manual seeding is strictly required to start, but
   agent recall improves after [`scripts/seed_memory.py`](#profile-cli-high-level).
4. **LLM (optional)** — Default `MODEL_PROVIDER=none` uses Vanna’s
   **`MockLlmService`** (no outbound HTTP). For real natural-language answers,
   set `MODEL_PROVIDER=openai_compatible` plus `MODEL_API_KEY`, `MODEL_BASE_URL`,
   and `MODEL_NAME` per `.env.example` (any OpenAI-compatible endpoint).

### 1. Create and activate the virtual environment

```bash
python -m venv .venv
```

```bash
# Linux / macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

Equivalent: `make install` (see [With `make`](#with-make)).

### 3. Configure environment

```bash
cp .env.example .env
```

```powershell
# Windows PowerShell (equivalent)
Copy-Item .env.example .env
```

Edit `.env`: set **`DB_*`** for your SQL Server instance, confirm **`DB_PROFILE_ID`**
matches an existing profile folder (e.g. `dbnwind`), and adjust **`CHROMA_PERSIST_DIR`**
if you do not want vectors under `.data/chroma`.

### 4. (Recommended) Lint and test

```bash
ruff check .
pytest
```

Equivalent: `make check`.

### 5. Start the app (API + UI)

**Development (one command, hot-reload UI):**

```bash
python scripts/dev.py
```

Equivalent: `make run` after `pip install -e ".[dev]"` and `cd web && npm install`.

Open **`http://127.0.0.1:5173`** — Vite serves the React app and proxies `/api`,
`/health`, and `/ready` to the API on port 8000. Press Ctrl+C to stop both processes.

**API only** (serves a pre-built UI from `web/dist` at `/app`; run `cd web && npm run build` after UI changes):

```bash
python scripts/dev.py --api-only
```

Equivalent: `make run-api` or `python -m vai_agent.cli.run_api`.

### 6. Verify

| URL | Expected |
|-----|----------|
| [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) | Always **`ok`** if the process is up (liveness). |
| [http://127.0.0.1:8000/ready](http://127.0.0.1:8000/ready) | **`status: ok`** only when profile load, Chroma memory, and DB-backed agent all initialise. HTTP **503** with `errors` if something failed (common: ODBC driver name, firewall, wrong password, or schema/profile mismatch). |

Interactive docs: **`/docs`** and **`/redoc`** when `APP_ENV=dev` (disabled in
`prod`).

### Optional next steps

- **Real LLM:** set model provider variables in `.env` (see [Optional: model provider](#optional-model-provider-openai-compatible-api) below).
- **Refresh Chroma from the profile:**  
  `python scripts/seed_memory.py --profile dbnwind`
- **New database / schema:** generate and validate a profile from DDL under
  `data/input/` — see [Profile CLI](#profile-cli-high-level) and
  [`docs/DATABASE_PROFILE_GUIDE.md`](./docs/DATABASE_PROFILE_GUIDE.md).

### Main HTTP routes (beyond health)

Sample **`GET /health`** body:

```json
{ "status": "ok", "app": "sql-assistant", "version": "0.1.0", "env": "dev" }
```

Agent tooling: **`GET /agent/tools`**,
**`POST /agent/tools/{tool_name}/invoke`** (rate-limited; requires a working SQL Server connection).

**Official web UI (production / API-only):** **`GET /app`** (static build from `web/dist`, or a
minimal “not built” page when `web/dist` is absent). **`GET /`** redirects to **`/app`**.

**Development:** use **`http://127.0.0.1:5173`** via `python scripts/dev.py` (not `/app` on :8000)
so the UI hot-reloads without rebuilding `web/dist`.

**`POST /api/v1/chat`** is the versioned UI/API entry point: it uses **`GuardedChatHandler`**
(subclass of Vanna **`ChatHandler`**) so rate limits, concurrency, prompt-injection checks, and audit
run **before** **`Agent.send_message`** (the full Vanna agent loop — not manual
`llm_service.send_request` / `tool_registry.execute`).

Supporting JSON under **`/api/v1`**: **`GET /api/v1/status`**, **`GET /api/v1/profile`**, **`GET /api/v1/tools`**.

**`POST /chat`** remains as an internal, **deprecated** alias of the same handler stack (for older
callers); new clients should use **`/api/v1/chat`**.

Vanna stock UI routes (**`/api/vanna/v2/*`**, bundled **`GET /`** HTML) are **not** registered.

### Optional: model provider (OpenAI-compatible API)

Set `MODEL_PROVIDER=openai_compatible`, `MODEL_API_KEY`, `MODEL_BASE_URL`, and
`MODEL_NAME` per `.env.example` (works with OpenRouter, LM Studio, LiteLLM, Ollama
OpenAI mode, etc.). The **Vanna** agent’s `llm_service` is built in
`vai_agent.vanna_integration.model_llm` via `OpenAILlmService`.
Use `MODEL_PROVIDER=none` for **`MockLlmService`** (no outbound HTTP).

Deprecated env names (`LLM_PROVIDER`, `OPENROUTER_*`) are still read when `MODEL_*`
is unset.

---

## With `make`

```bash
make install   # install deps into .venv
make lint      # ruff check
make test      # pytest
make check     # lint + test (CI-equivalent)
make run         # API + Vite dev (one command)
make run-api     # API only; UI from web/dist at /app
make web-install
make web-dev     # Vite only (if you need the UI process alone)
make web-build   # production bundle → web/dist
```

## Without `make`

All `make` targets resolve to direct calls against the `.venv` interpreter,
so any of the following work as drop-in replacements (PowerShell shown):

```powershell
.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\python.exe scripts\dev.py
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
├── web/                    # Vite + React first-party UI (build → web/dist)
├── src/vai_agent/
│   ├── main.py             # uvicorn imports `app`
│   ├── bootstrap.py        # app factory + startup wiring + web + API v1
│   ├── api/                # health (/health, /ready) + agent + /chat + /api/v1
│   ├── web/                # FastAPI helpers to serve /app
│   ├── channels/           # future Telegram / Discord adapters (skeleton)
│   ├── vai_app/            # Context enhancer + legacy sync Agent (tests only)
│   ├── vanna_integration/ # Vanna Agent factory, GuardedChatHandler (no stock HTTP UI)
│   ├── tools/              # SecureRunSql, ExplainSchema, ProfileSearch
│   ├── db/                  # ODBC connection + MSSQL runner + schema_extractor
│   ├── memory/              # Chroma persistent AgentMemory
│   ├── llm/                 # OpenAI-compatible chat completions
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
| `MODEL_PROVIDER`   | `none` / `openai_compatible` | Configures **Vanna** `llm_service` on `app.state.agent` |

See [SECURITY.md](./SECURITY.md) for production hardening (never commit `.env`,
forbid `USER_RESOLVER_MODE=dev` outside `APP_ENV=dev`, header auth behind a
trusted proxy, and `CORS_ORIGINS`).

See `.env.example` for the full annotated list (`USER_RESOLVER_MODE`,
`CONTEXT_MAX_TOKENS`, model base URL/timeouts, etc.).

---

## Roadmap

See [`PROGRESS.md`](./PROGRESS.md) for the live status of each phase. The
master specification lives in `vai-prompt.txt`.
