"""Thin wrapper exposing :mod:`vai_agent.cli.generate_profile` as a script.

Run from the repository root::

    python scripts/generate_profile_from_schema.py \
        --input data/input/Schema.sql \
        --profile dbnwind
"""

from __future__ import annotations

from vai_agent.cli.generate_profile import main

if __name__ == "__main__":
    raise SystemExit(main())
