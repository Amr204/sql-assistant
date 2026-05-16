# Operations

## Runtime Prerequisites

- Python 3.11+
- ODBC Driver 18 for SQL Server installed
- `.env` configured from `.env.example`
- Profile exists at `profiles/<DB_PROFILE_ID>`

## Startup

```powershell
uvicorn vai_agent.main:app --reload
```

On startup the app:

1. loads profile from `PROFILES_ROOT/DB_PROFILE_ID`
2. reads DB settings (`DB_*`) into `ConnectionSettings`
3. builds `UserResolver` from `USER_RESOLVER_MODE` + `DEV_USER_*`
4. builds agent and attaches `app.state.agent`
5. opens Chroma memory at `CHROMA_PERSIST_DIR`

## Health Endpoints

- `GET /health` → process liveness
- `GET /ready` → dependency readiness (`profile_ready`, `agent_ready`, `memory_ready`)

Readiness returns `503` when any required dependency failed startup.

## Common Checks

```powershell
ruff check .
pytest
python scripts/validate_profile.py --profile dbnwind
python scripts/benchmark_questions.py --profile dbnwind
```

## Troubleshooting

- `/agent/tools` returns `503`
  - check `GET /ready` and inspect `errors`
  - verify `DB_*` variables are present and valid
- profile load failure
  - verify `PROFILES_ROOT` and `DB_PROFILE_ID`
- memory failure
  - verify write permission on `CHROMA_PERSIST_DIR`
