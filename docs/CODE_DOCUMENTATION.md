# Code documentation standards

This project uses **PEP 257**-style docstrings in Python and brief module headers in TypeScript.
The goal is maintainability and safe change at **architectural seams**, not comment noise on every line.

## What to document

| Location | Required content |
|----------|------------------|
| **Package `__init__.py`** | Purpose of the package and its boundary (what it must not do). |
| **Security modules** (`security/`, `users/`, policy runners) | Threat model, violation codes, defense-in-depth order, fail-closed behaviour. |
| **Execution seam** (`db/mssql_runner.py`, `policy_sql_runner.py`) | Preconditions (SQL must be policy-approved), error sanitization rules. |
| **HTTP entrypoints** (`api/`, `bootstrap.py`) | Auth resolution, rate limits, request size limits, which handler owns chat. |
| **Frontend API layer** (`web/src/api/`) | Validation boundary, abort/retry behaviour, no secrets in storage. |

## Docstring style (Python)

- **Module**: one-line summary, then optional paragraphs for boundaries and security.
- **Public classes/functions**: summary line; `Parameters` / `Returns` / `Raises` when non-obvious.
- Use imperative mood: *"Return the validated user."* not *"Returns..."* in the one-liner (PEP 257 allows either; we prefer imperative for summaries).

## Inline comments

Use sparingly for:

1. **Security rationale** — why a check exists and what happens if it is removed.
2. **Non-obvious tradeoffs** — conservative false positives vs false negatives.
3. **Ordering dependencies** — e.g. prompt injection before LLM, SQL policy before execute.

Do **not** restate the code (`# increment i`).

## Architectural boundaries

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the layer diagram and allowed dependencies.
**Rule:** outer layers depend inward; `security/` and `knowledge/profile_models` never import `db/` or `vanna`.

## Frontend

- UI components stay dumb; **validation and fetch policy** live under `web/src/api/`.
- Persisted chat stores metadata only (no full result rows) — documented in `usePersistedChat.ts`.
- Exported functions in `web/src/api/`, `web/src/hooks/`, and `web/src/lib/` use brief **JSDoc** (`/** … */`) on the symbol or module header.

## Maintaining Python docstrings

To fill missing one-line docstrings on public functions and classes under `src/vai_agent/`:

```bash
uv run python scripts/add_missing_docstrings.py
```

The script is idempotent (skips symbols that already have docstrings). Prefer hand-written summaries on security-critical paths (`security/`, `api/v1/chat.py`, rate limiting); extend `OVERRIDES` in the script for stable names.

Audit coverage:

```bash
uv run python -m compileall -q src
uv run pytest -q
```

## Related docs

- [ARCHITECTURE.md](./ARCHITECTURE.md) — system design and seams
- [SECURITY.md](../SECURITY.md) — deployment hardening
- [OPERATIONS.md](./OPERATIONS.md) — runbooks
