# Web UI (`web/src`)

React + TypeScript client for SQL Assistant. Talks to the FastAPI backend via
`/api/v1` (Vite dev proxy → port 8000).

## Layer boundaries

| Directory | Role |
|-----------|------|
| `api/` | HTTP client, response validation, typed DTOs — **trust but verify** server JSON |
| `hooks/` | Chat state, persistence policy, request lifecycle (abort, generation id) |
| `features/` | Screens and panels (chat, diagnostics, tools drawer) |
| `components/` | Reusable UI primitives |
| `lib/` | Cross-cutting helpers (CSV export, startup retry) |

Security / privacy:

* No secrets in `localStorage` — see `hooks/usePersistedChat.ts`
* SQL highlighting sanitized before `dangerouslySetInnerHTML` — `components/sanitizePrismHtml.ts`
* Errors from the API are validated before rendering tables — `api/validate.ts`

Architecture overview: [../../docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).
