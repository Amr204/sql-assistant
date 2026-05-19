# COMPATIBILITY — Vanna 2.0.2 API (source-derived)

This file lists **actual module paths and class names** from the installed
**Vanna 2.0.2** package (same layout as the official `vanna-2.0.2` sdist / wheel).
The project does **not** ship `vanna-2.0.2.zip` in-repo; paths below were taken
from `site-packages/vanna/` and cross-checked with [vanna.ai/docs](https://vanna.ai/docs/).

**Note:** `vanna.__version__` in the package is the string `"0.1.0"` even for the
2.0.2 release; use `import importlib.metadata as m; m.version("vanna")` for the
PyPI version.

---

## Core agent & tools

| Concept | Canonical import (2.0.2 source) |
|--------|-----------------------------------|
| Agent | `from vanna.core.agent import Agent` — implementation in `vanna.core.agent.agent` |
| Agent config | `from vanna.core.agent import AgentConfig` |
| Tool registry | `from vanna.core.registry import ToolRegistry` — defined in `vanna.core.registry` |
| Tool ABC | `from vanna.core.tool import Tool` — `vanna.core.tool.base` |
| Tool models | `from vanna.core.tool import ToolCall, ToolContext, ToolResult, ToolSchema` — `vanna.core.tool.models` |
| Register tools | `ToolRegistry.register_local_tool(tool, access_groups: list[str])` |

Public re-exports also appear on `vanna.core` (`from vanna.core import Agent, ToolRegistry, ToolCall, …`).

---

## SQL execution

| Concept | Canonical import |
|--------|------------------|
| Run SQL tool | `from vanna.tools.run_sql import RunSqlTool` — also `from vanna.tools import RunSqlTool` |
| SQL runner ABC | `from vanna.capabilities.sql_runner import SqlRunner` — `vanna.capabilities.sql_runner.base` |
| Run SQL args model | `from vanna.capabilities.sql_runner import RunSqlToolArgs` — `vanna.capabilities.sql_runner.models` |

This app injects a custom `SqlRunner` (`PolicySqlRunner`) that applies local SQL/PII policy **before** any database call, then exposes it through **two** `RunSqlTool` registrations: primary **`run_sql`** and optional alias **`secure_run_sql`** (same runner, same `access_groups`). Both tools receive a **`LocalFileSystem`** whose ``working_directory`` is ``Settings.vanna_file_storage_dir`` (default ``.data/vanna_files``) so Vanna’s ``query_results_*.csv`` files never land in the project root.

---

## Agent memory (persistent Chroma)

| Concept | Canonical import |
|--------|------------------|
| AgentMemory ABC | `from vanna.capabilities.agent_memory import AgentMemory` — `vanna.capabilities.agent_memory.base` |
| Memory models | `from vanna.capabilities.agent_memory import TextMemory, ToolMemory, …` — `vanna.capabilities.agent_memory.models` |
| **Official Chroma implementation** | `from vanna.integrations.chromadb import ChromaAgentMemory` — implementation in `vanna.integrations.chromadb.agent_memory` |

`ChromaAgentMemory` uses `chromadb.PersistentClient` internally (`persist_directory`, `collection_name`, optional `embedding_function`). This app sets `persist_directory` to `CHROMA_PERSIST_DIR` and `collection_name` to `vanna_agent_<profile_id>`.

Other first-party memory backends in the same tree (not used here): `WeaviateAgentMemory`, `QdrantAgentMemory`, `FAISSAgentMemory`, `PineconeAgentMemory`, `MilvusAgentMemory`, `MarqoAgentMemory`, `OpenSearchAgentMemory`, `AzureAISearchAgentMemory`, `CloudAgentMemory` (premium), and in-memory `DemoAgentMemory` under `vanna.integrations.local.agent_memory`.

---

## User resolution

| Concept | Canonical import |
|--------|------------------|
| UserResolver ABC | `from vanna.core.user import UserResolver` — `vanna.core.user.resolver` |
| User model | `from vanna.core.user import User` — `vanna.core.user.models` |
| Request context | `from vanna.core.user import RequestContext` — `vanna.core.user.request_context` |

This app supplies `LegacyUserResolverBridge(UserResolver)` wrapping `vai_agent.users.UserResolver`.

---

## LLM (OpenAI-compatible model provider)

| Concept | Canonical import |
|--------|------------------|
| LlmService ABC | `from vanna.core.llm import LlmService` — `vanna.core.llm.base` |
| Request/response models | `from vanna.core.llm import LlmRequest, LlmResponse, LlmMessage, LlmStreamChunk` |
| OpenAI-compatible client | `from vanna.integrations.openai import OpenAILlmService` — class in `vanna.integrations.openai.llm` (`base_url`, `api_key`, `model`, …) |
| Mock LLM | `from vanna.integrations.mock import MockLlmService` |

---

## FastAPI server (stock Vanna)

| Concept | Canonical import |
|--------|------------------|
| FastAPI factory | `from vanna.servers.fastapi import VannaFastAPIServer` — `vanna.servers.fastapi.app` |
| Chat handler | `from vanna.servers.base import ChatHandler` (re-exported from `vanna.servers`) |
| Chat request/response | `from vanna.servers.base import ChatRequest, ChatResponse` |
| Route registration (stock) | `from vanna.servers.fastapi.routes import register_chat_routes` — mounts **`POST /api/vanna/v2/chat_poll`**, **`POST /api/vanna/v2/chat_sse`**, **`WS /api/vanna/v2/chat_websocket`**, and stock **`GET /`** (bundled UI) |
| Route registration (this repo) | `from vai_agent.vanna_integration.vanna_fastapi_routes import register_chat_routes` — same paths; re-raises **`HTTPException`** from the chat handler so 401/400/429 are not coerced into 500 |

This repository keeps its own FastAPI app (`vai_agent.bootstrap.create_app`) and first-party routes (`/agent/*`, `/health`, `/ready`). **`POST /chat`** and the official Vanna routes use **`GuardedChatHandler`**, a subclass of **`ChatHandler`** that overrides **`handle_stream`** to apply user resolution, rate limits, concurrency, prompt-injection checks, and audit records **before** **`Agent.send_message`**. The handler passed to **`register_chat_routes`** is that **`GuardedChatHandler`** instance.

**SSE / WebSocket note:** when limits or injection checks fail inside the streaming generator, stock Vanna would surface some failures only as SSE JSON errors. This fork re-raises **`HTTPException`** from **`chat_poll`**; for **`chat_sse`**, failures on the first stream chunk may still be delivered as an SSE error payload depending on ASGI behaviour—prefer **`chat_poll`** for strict HTTP status codes.

## Runtime API inspect (installed vanna; May 2026)

Captured with `uv run python` against the locked environment:

- `vanna.__file__` → site-packages `vanna/__init__.py`
- `inspect.signature(Agent)` → constructor takes `llm_service`, `tool_registry`, `user_resolver`, `agent_memory`, optional `conversation_store`, `config`, `system_prompt_builder`, `lifecycle_hooks`, `llm_middlewares`, optional `workflow_handler`, `error_recovery_strategy`, `context_enrichers`, optional `llm_context_enhancer`, `conversation_filters`, optional `observability_provider`, optional `audit_logger`
- `inspect.signature(ChatHandler)` → `(agent: vanna.core.agent.agent.Agent)`
- `dir(ChatHandler)` stream/poll API: **`handle_poll`**, **`handle_stream`**
- `vanna.tools.run_sql` → package module `vanna.tools.run_sql`
- `inspect.signature(ToolRegistry.register_local_tool)` → `(self, tool: Tool[Any], access_groups: List[str]) -> None`

The vendored tree `vanna-2.0.2/` in this workspace mirrors the PyPI 2.0.2 layout for offline reference; **ruff** excludes it from lint (`pyproject.toml` `extend-exclude`).

---

| Concept | Canonical import |
|--------|------------------|
| In-memory store | `from vanna.integrations import MemoryConversationStore` — `vanna.integrations.local` |

---

## Legacy stack (Vanna 0.x)

Under `vanna.legacy.*` (e.g. `vanna.legacy.chromadb.ChromaDB_VectorStore`, `vanna.legacy.base.VannaBase`). **Not used** by this project’s 2.x Agent path.
