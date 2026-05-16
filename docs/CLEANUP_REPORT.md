# CLEANUP_REPORT — Final hardening (May 2026)

## Runtime / delivery hygiene

- **`.gitignore`** extended with `*.sqlite`, `*.db`, `query_results_*.csv`, and a top-level `reports/` ignore for generated artefacts.
- **`scripts/clean_runtime_artifacts.ps1`** and **`scripts/clean_runtime_artifacts.sh`** remove `.data`, tool caches, `__pycache__`, `*.pyc`/`*.pyo`/`*.log`, and `query_results_*.csv`, while **skipping `.venv`** (and **`vanna-2.0.2`** in the shell script) so local interpreters are not destroyed.
- **`.env`** must never be committed; contract tests skip the “no `.env`” probe when a developer has a local file.

## Vanna RunSqlTool CSV sink

- **`Settings.vanna_file_storage_dir`** (default **`.data/vanna_files`**) is passed to **`vanna.integrations.local.LocalFileSystem(working_directory=…)`** for both **`run_sql`** and **`secure_run_sql`** tool registrations in **`vanna_integration/factory.py`**.

## Bootstrap

- **`app.state.llm_service`** and **`build_chat_completion_client`** were removed from **`bootstrap.py`**. The only production LLM handle is **`runtime.vanna.llm_service`** on **`app.state.agent`** (`VaiVannaRuntime`).

## Legacy code

- **`vai_app/`** (sync `Agent`, `ToolRegistry`, **`ContextEnhancer`**) remains **imported** by **`vanna_integration/factory.py`** and **unit tests**; it is **not** the HTTP runtime path. **`agent_factory.py`** already documents test-only use.
- **`vai_agent/tools/base.py`** and **`llm/`** remain in use (profile tools, OpenRouter client tests).

## Tests added

- `tests/test_cleanup_contract.py`, `test_vanna_file_storage.py`, `test_no_legacy_runtime.py`, `test_vanna_routes_guarded.py`, `test_run_sql_tool_contract.py`
- **`test_bootstrap_startup`** now asserts **`app.state.agent`** is a **`VaiVannaRuntime`**.

## Not done here

- **`.git/`** is never deleted from a developer working copy; exclude it from release zips manually or via CI packaging.
