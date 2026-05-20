"""Start uvicorn with dev reload settings.

Uses ``uvicorn.run()`` instead of the CLI so glob patterns in ``--reload-exclude``
are not expanded by Click on Windows (see Click ``windows_expand_args``).
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[3]

# Narrow reload scope so logs/audit/artifacts do not trigger restart loops.
RELOAD_DIRS = ["src", "profiles"]
RELOAD_EXCLUDES = [
    "logs/*",
    "audit/*",
    "activity_audit/*",
    ".data/*",
    "web/dist/*",
    "*.xlsx",
    "*.csv",
    "*.jsonl",
]


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    env_path = REPO_ROOT / ".env"
    uvicorn.run(
        "vai_agent.main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=RELOAD_DIRS,
        reload_excludes=RELOAD_EXCLUDES,
        env_file=str(env_path) if env_path.is_file() else None,
    )


if __name__ == "__main__":
    main()
