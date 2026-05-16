# COMPATIBILITY

Status of third-party API choices and how they map to the master spec
(`vai-prompt.txt`). Updated whenever a phase introduces or changes a
dependency.

---

## Vanna 2.0 — not installed (intentional)

The master spec asks the project to follow Vanna 2.0's design:
`Agent`, `ToolRegistry`, `RunSqlTool`, `AgentMemory`, `UserResolver`,
`AgentConfig`, `AuditConfig`, conversation filters, LLM context
enhancers, and UI feature flags.

**Decision (Phase 6): the `vanna` Python package is _not_ a dependency
of this project.** We mirror Vanna's design with our own minimal
abstractions inside `src/vai_agent/`.

### Why

1. **Discipline rule from the master spec:** "Use the API actually
   available in the installed version. Do not invent class names. If
   the documentation differs from the installed package, document it
   in `COMPATIBILITY.md`." — Section 20 of `vai-prompt.txt`.
2. **Scope:** Phase 6 focused on tools + HTTP. **ChromaDB-backed memory**
   and **`vai_agent.llm.*` (OpenRouter over `httpx`)** now exist for downstream
   NL→SQL work; full LLM planning **above** ``Agent.invoke`` is still wiring a
   consumer, not bundled as a turnkey HTTP feature.
3. **Coupling cost:** `vanna` pins `chromadb`, `openai`, `sqlalchemy`
   and a number of optional vector backends. Installing it now would
   constrain dependency versions before we know exactly which Vanna
   sub-modules we will keep.
4. **Stability:** Vanna's API has churned across 2.x releases. By
   building our own thin `ToolBase` / `Agent` / `ToolRegistry` and
   keeping them at the package boundary, a future Vanna adapter can
   sit *behind* this interface without rewriting callers.

### Mapping our types to Vanna 2.0 concepts

| Vanna 2.0 concept           | This project                                                |
| --------------------------- | ----------------------------------------------------------- |
| `Agent`                     | `vai_agent.vai_app.agent_factory.Agent`                     |
| `ToolRegistry`              | `vai_agent.vai_app.tool_registry.ToolRegistry`              |
| `RunSqlTool` (LLM-friendly) | `vai_agent.tools.SecureRunSqlTool`                          |
| `Tool` base class           | `vai_agent.tools.base.ToolBase`                             |
| `ToolResult`                | `vai_agent.tools.base.ToolResult`                           |
| `UserResolver`              | `vai_agent.users.UserResolver`                              |
| Schema explainer            | `vai_agent.tools.ExplainSchemaTool`                         |
| Knowledge search            | `vai_agent.tools.ProfileSearchTool`                         |
| `AgentMemory` (persistent)  | `vai_agent.memory.memory_factory.AgentMemory` — Chroma `PersistentClient` |
| LLM context enhancer        | `vai_agent.vai_app.context_enhancer.ContextEnhancer` (Phase 8) |
| Conversation filters        | _Not implemented yet — partly subsumed by `SqlPolicyEngine`_|
| `AuditConfig`               | _Not implemented yet — Phase 6's logging only_              |
| UI feature flags            | _Not implemented yet_                                       |

### How to add real Vanna later

The recommended adapter shape:

```python
# Sketch (NOT yet implemented).
from vanna.base import VannaBase
from vai_agent.tools.base import ToolBase

class VannaRunSqlAdapter(ToolBase):
    name = "vanna_run_sql"
    args_model = SecureRunSqlArgs
    def __init__(self, vn: VannaBase, ...): ...
    def execute(self, args, user): ...
```

Then register it alongside (or instead of) `SecureRunSqlTool` in the
agent factory. Everything else (HTTP, registry, user resolver, access
groups) stays unchanged.

---

## Installed versions of relevant dependencies

| Package           | Pinned range            | Installed (verified at Phase 6)   | Notes                                                  |
| ----------------- | ----------------------- | --------------------------------- | ------------------------------------------------------ |
| `fastapi`         | `>=0.115,<1.0`          | 0.136.1                           | Stable API surface used.                               |
| `pydantic`        | `>=2.7,<3.0`            | 2.13.4                            | v2 only; uses `model_dump`, `model_validate`, `model_copy`. |
| `pydantic-settings` | `>=2.3,<3.0`          | 2.14.1                            | Used for `BaseSettings` in both `Settings` and `ConnectionSettings`. |
| `sqlglot`         | `>=20.0`                | 30.8.0                            | `walk()` yields **plain nodes** in 30.x (not `(node, parent, key)` tuples). Documented in `sql_policy.py`. |
| `pyodbc`          | `>=5.0,<6.0`            | 5.3.0                             | DSN-less connection string. `ApplicationIntent=ReadOnly` always appended. |
| `pandas`          | `>=2.0,<3.0`            | 2.3.3                             | Used for `read_sql(chunksize=...)`; `pd.NaT` and numpy scalars normalised in the runner. |
| `pyyaml`          | `>=6.0,<7.0`            | 6.0.3                             | `safe_load` / `safe_dump` only; `allow_unicode=True` for Arabic content. |
| `vanna`           | _not installed_         | —                                 | Intentional. See section above.                        |
| `openai`          | _not installed_         | —                                 | Not required — OpenRouter is called with raw `POST /chat/completions` via **`httpx`**. |
| `httpx`           | `>=0.27,<1.0` (runtime) | —                                 | OpenAI-compatible OpenRouter HTTP client in `llm/openrouter_service.py`; also used implicitly by FastAPI test clients when applicable. |
| `chromadb`        | `>=1.5,<2.0`            | 1.5.9                             | Phase 7. 0.6.x was incompatible with pydantic 2.13.x (see note). 1.5.x custom EFs require `name()`, `embed_query()`, `embed_documents()` in addition to `__call__`. |

---

## API quirks worth recording

These are non-obvious behaviours of the *installed* package versions
that this project relies on. If a future upgrade changes any of them,
the documented behaviour must be re-verified.

### `sqlglot` 30.x

* `expression.walk()` is a flat iterator over nodes, not a
  `(node, parent, key)` tuple iterator.
* `SELECT TOP N` parses into a `Select` with `args["limit"]` of type
  `exp.Limit` (no separate `Top` node).
* Three-part table names map to `Table(this=…, db=schema, catalog=database)`
  — we treat any non-empty `catalog` as a cross-database reference.
* `COUNT(*)` contains an `exp.Star` node. The SQL policy currently
  blocks any `Star` reference — a conservative choice, documented as a
  Phase-7+ refinement.

### `pyodbc` 5.3.0

* `pyodbc.Connection` has no Python-visible attribute named `timeout`
  on the *class*; the attribute is set on instances after connect and
  controls query-level deadlines.
* SQLSTATE for client-side timeouts is `HYT00`; SQL Server's
  query-cancel is `HY008`. The runner accepts both.

### `pandas` 2.3.3

* `pd.read_sql(chunksize=N)` returns a generator; we consume it with
  a manual loop instead of relying on `len(df)` semantics that differ
  between scalar and chunked returns.
* `pd.NaT` is the only non-scalar nullable value the runner has to
  special-case during normalisation.

---

### `chromadb` 0.6.3 vs 1.5.9

We initially installed `chromadb>=0.5,<1.0` (got 0.6.3).  It was
incompatible with pydantic 2.13.x: `chromadb.types.Collection.get_model_fields()`
called `self.model_fields` on an **instance** rather than the class,
which pydantic 2.13 surfaces as a `DeprecatedInstanceProperty` object
instead of a dict → `AttributeError`.  We upgraded to `chromadb>=1.5,<2.0`
(got 1.5.9).

API changes in 1.5.x for custom `EmbeddingFunction` subclasses:

| Method         | 0.6.x | 1.5.x |
| -------------- | ----- | ----- |
| `__call__`     | required (used for both add and query) | still called for add |
| `embed_query`  | not required | **required** for `query()` calls |
| `embed_documents` | not required | required for `add()` / `upsert()` |
| `name()`       | not required | **required** for collection validation |
| `__init__()`   | optional | **required** (deprecation warning if absent) |

The `DummyEF` in tests implements all five.  The production path uses
`DefaultEmbeddingFunction` (all-MiniLM-L6-v2 via ONNX, auto-cached in
`~/.cache/chroma/onnx_models/`), which already satisfies the 1.5.x protocol.

## Items deliberately deferred

The following spec items from `vai-prompt.txt` are **not** implemented
in Phase 6; each lists which phase will pick it up:

| Spec item                           | Planned phase |
| ----------------------------------- | ------------- |
| OpenRouter / OpenAI-compatible LLM  | Phase 7       |
| Custom LLM context enhancer         | Phase 8 (done) |
| LLM-driven planner (NL → tool call) | Phase 7       |
| `AgentMemory` (ChromaDB)            | Phase 7       |
| Memory seeding script               | Phase 7       |
| `examples.yaml` benchmark runner    | Phase 9 (`scripts/benchmark_questions.py`) |
| Rate limiting (per user / IP / group)| Phase 8      |
| Audit log persistence               | Phase 8       |
| FastAPI Web UI                      | Phase 9       |
| OIDC / JWT user resolver            | Phase 9       |
| Mermaid diagrams in `ARCHITECTURE.md` | Phase 9     |
