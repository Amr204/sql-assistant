# PROGRESS

Live tracker for the phased delivery of SQL Assistant. The master spec is
`vai-prompt.txt`; this file records what is **actually** done in the repo.

---

## Current phase

**Phase 3 — Schema-to-profile generator. Status: ✅ complete (lint + 116 tests green; real DBnwind profile generated and validated).**

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

| Phase | Status   | Notes                                                                              |
| ----- | -------- | ---------------------------------------------------------------------------------- |
| 1     | done     | Foundations: skeleton, settings, logging, `/health`, tests, ruff.                  |
| 2     | done     | Profile models, loader, validators, CLI, 45 new tests.                             |
| 3     | done     | Schema extractor + profile generator + CLI; 62 new tests; real DBnwind generated.  |
| 4+    | planned  | See _Next phase_ above.                                                            |
