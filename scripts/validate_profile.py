"""Thin wrapper exposing :mod:`vai_agent.cli.validate_profile` as a script.

Run from the repository root::

    python scripts/validate_profile.py --profile default
"""

from __future__ import annotations

from vai_agent.cli.validate_profile import main

if __name__ == "__main__":
    raise SystemExit(main())
