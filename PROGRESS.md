# PROGRESS

Live tracker for the phased delivery of SQL Assistant. The master spec is
`vai-prompt.txt`; this file records what is **actually** done in the repo.

---

## Current phase

**Phase 2 — Profile models, loader, validators. Status: ✅ complete (lint + 54 tests green).**

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

**Phase 3 — Profile generation from SQL schema (planned, not started).**

Tentative deliverables (subject to confirmation before kickoff):

- `src/vai_agent/db/schema_extractor.py` — parse `data/input/schema.sql`
  (raw DDL) into intermediate structures.
- `src/vai_agent/knowledge/schema_analyzer.py` — classify tables (fact /
  dimension / lookup / audit / config), infer relationships.
- `src/vai_agent/knowledge/profile_generator.py` — emit each
  `profiles/<profile_id>/*.yaml` from the analyzed schema, using the
  Phase-2 Pydantic models as the writer's source of truth (so anything
  it produces is loadable by `ProfileLoader` and passes
  `validate_profile`).
- `scripts/generate_profile_from_schema.py` CLI.
- Tests using a small DDL fixture; round-trip
  generate → load → validate must yield 0 errors.

Vanna integration itself is **Phase 4+** — it should not start until
the full profile pipeline (generate → validate → seed) is verified.

---

## Phase log

| Phase | Status   | Notes                                                              |
| ----- | -------- | ------------------------------------------------------------------ |
| 1     | done     | Foundations: skeleton, settings, logging, `/health`, tests, ruff.  |
| 2     | done     | Profile models, loader, validators, CLI, 45 new tests.             |
| 3+    | planned  | See _Next phase_ above.                                            |
