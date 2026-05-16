"""Thin wrapper exposing :mod:`vai_agent.cli.seed_memory` as a script.

Run from the repository root::

    python scripts/seed_memory.py --profile dbnwind
    python scripts/seed_memory.py --profile dbnwind --force
"""

from __future__ import annotations

from vai_agent.cli.seed_memory import main

if __name__ == "__main__":
    raise SystemExit(main())
