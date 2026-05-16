# Progress (docs mirror)

The full phased delivery tracker lives at **[`../PROGRESS.md`](../PROGRESS.md)** in the repository root.

## Vanna 2.x alignment snapshot (runtime)

- **`POST /chat`** — **`GuardedChatHandler`** (Vanna **`ChatHandler`** subclass) → **`Agent.send_message`** (no manual `LlmService.send_request` / `ToolRegistry.execute` in this route).
- **Official Vanna HTTP** — `register_chat_routes` (fork in **`vanna_fastapi_routes`**) with the same **`GuardedChatHandler`** exposes **`POST /api/vanna/v2/chat_poll`**, **`chat_sse`**, **`chat_websocket`**.
- **Tools** — primary **`run_sql`** plus **`secure_run_sql`** alias; schema/search tools; **non-empty** `access_groups` from `security_policy`.
- **RunSql CSV sink** — **`LocalFileSystem`** rooted at **`Settings.vanna_file_storage_dir`** (default **`.data/vanna_files`**).
- **Memory tools** — `SearchSavedCorrectToolUsesTool` (analyst/admin); `SaveQuestionToolArgsTool` / `SaveTextMemoryTool` (admin only), from `vanna.tools.agent_memory`.
- **Audit** — `JsonlVannaAuditLogger` redacts SQL and sensitive keys before JSONL emit.
- **Rate limits** — sliding windows on **`/chat`** and **`POST /agent/tools/{tool}/invoke`** (user, IP, group, daily, concurrency).

See also **[`COMPATIBILITY.md`](COMPATIBILITY.md)** for import paths against the installed **Vanna 2.0.2** package layout.
