# SQL Assistant

A Vanna-powered SQL Assistant for safe, profile-driven querying of SQL Server
databases. Long-term goal: turn natural-language questions (Arabic / English)
into validated, audited, read-only `SELECT` statements over a known schema.

> **Status — Phase 1 (foundations only).**
> Only the project skeleton, configuration, logging, and `/health` endpoint
> are implemented. Vanna integration, profile generation, secure SQL
> execution, and memory seeding are intentionally **not** wired up yet — see
> [`PROGRESS.md`](./PROGRESS.md) for the phased roadmap.

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

# 3. Configure environment
cp .env.example .env          # then edit .env as needed

# 4. Run the test suite + linter
ruff check .
pytest

# 5. Start the FastAPI app
uvicorn vai_agent.main:app --reload
```

Open <http://127.0.0.1:8000/health> — you should see:

```json
{ "status": "ok", "app": "sql-assistant", "version": "0.1.0", "env": "dev" }
```

Interactive API docs are available at `/docs` (disabled automatically when
`APP_ENV=prod`).

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

## Project layout (Phase 1)

```text
sql-assistant/
├── pyproject.toml          # build + tooling config (ruff, pytest)
├── .env.example            # documented environment variables
├── Makefile                # convenience targets
├── PROGRESS.md             # phase tracker (current + completed + next)
├── README.md
├── src/
│   └── vai_agent/
│       ├── __init__.py
│       ├── main.py         # ASGI entry: `uvicorn vai_agent.main:app`
│       ├── bootstrap.py    # FastAPI app factory
│       ├── config/
│       │   ├── settings.py        # Pydantic v2 BaseSettings
│       │   └── logging_config.py  # text / JSON logging
│       └── api/
│           └── health.py   # GET /health
└── tests/
    ├── conftest.py
    ├── test_settings.py
    ├── test_logging_config.py
    └── test_health.py
```

Folders for later phases (`llm/`, `db/`, `tools/`, `memory/`, `knowledge/`,
`security/`, `users/`, `profiles/`, `scripts/`, `docs/`) will be created
**when their phase begins**, to keep the repo free of empty placeholders.

---

## Configuration

All configuration is environment-driven. See [`.env.example`](./.env.example)
for the full list. Phase 1 keys:

| Variable      | Default       | Notes                                        |
| ------------- | ------------- | -------------------------------------------- |
| `APP_ENV`     | `dev`         | One of `dev`, `staging`, `prod`              |
| `APP_HOST`    | `127.0.0.1`   | HTTP bind host                               |
| `APP_PORT`    | `8000`        | HTTP bind port (1..65535)                    |
| `LOG_LEVEL`   | `INFO`        | `DEBUG` / `INFO` / `WARNING` / `ERROR`       |
| `LOG_FORMAT`  | `text`        | `text` (human) or `json` (structured)        |

When `APP_ENV=prod`, `/docs` and `/redoc` are disabled automatically.

---

## Roadmap

See [`PROGRESS.md`](./PROGRESS.md) for the live status of each phase. The
master specification lives in `vai-prompt.txt` and is the source of truth
for what every future phase must deliver.
