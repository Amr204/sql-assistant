# Progress (docs mirror)

The full phased delivery tracker lives at **[`../PROGRESS.md`](../PROGRESS.md)** in the repository root.

## Vanna 2.x alignment snapshot (runtime)

- **`POST /chat`** — `vanna.servers.base.ChatHandler.handle_poll` → **`Agent.send_message`** (no manual `LlmService.send_request` / `ToolRegistry.execute` in this route).
- **Official Vanna HTTP** — `register_chat_routes` exposes **`POST /api/vanna/v2/chat_poll`**, **`POST /api/vanna/v2/chat_sse`**, **`WS /api/vanna/v2/chat_websocket`** (and stock **`GET /`** UI when mounted).
- **Tools** — `secure_run_sql`, schema, and search tools register with **non-empty** `access_groups` from `security_policy` (optional `tool_access_groups` map).
- **Memory tools** — `SearchSavedCorrectToolUsesTool` (analyst/admin); `SaveQuestionToolArgsTool` / `SaveTextMemoryTool` (admin only), from `vanna.tools.agent_memory`.
- **Audit** — `JsonlVannaAuditLogger` redacts SQL and sensitive keys before JSONL emit.
- **Rate limits** — sliding windows on **`/chat`** and **`POST /agent/tools/{tool}/invoke`** (user, IP, group, daily, concurrency).

See also **[`COMPATIBILITY.md`](COMPATIBILITY.md)** for import paths against the installed **Vanna 2.0.2** package layout.
