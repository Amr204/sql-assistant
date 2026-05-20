# Security Hardening Status

This document describes the effective runtime security controls in Phase 10.

## Enforced Controls

- **SELECT-only SQL gate** via `SqlPolicyEngine` (`POL001`..`POL014`)
- **Vanna audit JSONL** via `JsonlVannaAuditLogger` with **SQL redaction** (no raw SQL in payloads; `sql_hash` + `[REDACTED_SQL]`)
- **In-process rate limits** on `POST /chat` and `POST /agent/tools/.../invoke` (per user, IP, group, rolling daily budget, concurrency cap)
- **No wildcard projection** (`SELECT *`, `c.*`) while allowing `COUNT(*)`
- **Blocked schemas/functions/features**
  - `sys`, `INFORMATION_SCHEMA`
  - `OPENROWSET`, `OPENQUERY`, `xp_cmdshell`, ...
  - profile-driven `blocked_sql_features`
- **Allow-list enforcement**
  - `allowed_schemas`
  - `allowed_tables`
- **Row-filter enforcement**
  - profile ``row_filters`` apply when the caller's group matches ``applies_to_groups``.
  - **Conservative validation**: the required predicate must appear in the **parsed ``WHERE``**
    clause text (sqlglot T-SQL). **UNION** queries cannot be proven and are rejected when a
    filter applies. **Automatic SQL rewriting is not enabled**; if a predicate cannot be
    proven, the query is rejected.
- **PII/sensitive/secret column checks** via ``PiiPolicyEngine`` with **group-aware** access
  (``admin`` for secrets; ``admin`` / ``pii_reader`` for PII; ``admin`` / ``security`` for sensitive)
- **Result shaping** (post-execution, before returning to the LLM): ``masking_rules`` and a
  **basic** ``min_group_size`` filter on count-like columns (not a formal privacy guarantee)
- **Read-only DB access intent**
  - ODBC connection string uses `ApplicationIntent=ReadOnly`
- **Vanna ``RunSqlTool`` CSV exports**
  - ``LocalFileSystem(working_directory=…)`` is pinned to ``Settings.vanna_file_storage_dir``
    (default ``.data/vanna_files``). Per-user hash subfolders hold ``query_results_*.csv`` — never
    the repository root. Remove with ``scripts/clean_runtime_artifacts.*`` before shipping; no
    automatic TTL (operational purge only).

## Not Yet Enforced (Known Gaps)

- **Formal privacy guarantees** for ``min_group_size`` (current logic only filters obvious
  low-count aggregate rows).
- **Automatic SQL rewrite** to inject row-filter predicates (still validation-only).

## Recommended Production Setup

- **Never commit `.env`** — copy from `.env.example` and keep secrets out of git
- Use dedicated SQL read-only account in `.env` (`DB_USERNAME`/`DB_PASSWORD`)
- Keep `DB_TRUST_SERVER_CERTIFICATE=false` in production
- **`APP_ENV=prod` or `staging`** — startup rejects `USER_RESOLVER_MODE=dev`
- Set `USER_RESOLVER_MODE=header` **only behind a trusted reverse proxy** that strips
  spoofed `X-User-*` headers and sets identity from verified authentication. Do not
  expose header mode directly to the public internet. The API never grants `admin` /
  `superadmin` / `root` from raw headers.
- Chat requests are checked for obvious prompt-injection patterns; **SQL policy remains
  the execution barrier** regardless of prompt heuristics.
- Set `CORS_ORIGINS` to explicit HTTPS origins (no `*` wildcard in production)
- Restrict network path from API host to SQL Server
- Enable centralized log shipping for policy violations and query audits

## Local development vs production

| Setting | Local (`APP_ENV=dev`) | Production / staging |
|--------|------------------------|----------------------|
| `USER_RESOLVER_MODE` | `dev` (fixed user from `DEV_USER_*`) | `header` (or future OIDC) |
| `DEV_USER_GROUPS` | e.g. `analyst` or `admin` for testing | N/A (dev mode blocked) |
| `CORS_ORIGINS` | Optional; localhost:5173 always allowed | Required explicit origins |
| API docs | `/docs` enabled | Disabled when `APP_ENV=prod` |

Run locally: configure `.env`, start API (`make dev` or `uvicorn`), start web UI on port 5173.
Run production: set `APP_ENV=prod`, non-dev resolver, `CORS_ORIGINS`, and read-only DB credentials.
