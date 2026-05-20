"""``seed_memory`` CLI — seed a profile into ChromaDB.

Usage::

    python scripts/seed_memory.py --profile dbnwind
    python scripts/seed_memory.py --profile dbnwind --force
    python scripts/seed_memory.py --profile sample \\
        --profiles-root tests/fixtures/profiles \\
        --persist-dir .data/chroma_test

Exit codes:

* ``0`` — seed completed successfully
* ``1`` — profile not found or seeding failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from vai_agent.memory.seed_memory import seed_profile_memory


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_memory",
        description="Chunk a database profile and upsert it into ChromaDB.",
    )
    parser.add_argument(
        "--profile", required=True,
        help="Profile id (directory name under --profiles-root).",
    )
    parser.add_argument(
        "--profiles-root", default=Path("profiles"), type=Path,
        help="Root directory containing profile directories (default: ./profiles).",
    )
    parser.add_argument(
        "--persist-dir", default=Path(".data/chroma"), type=Path,
        help="ChromaDB persistence directory (default: .data/chroma).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Wipe the collection before seeding (full re-seed).",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Main."""
    out = stdout or sys.stdout
    err = stderr or sys.stderr

    args = _build_parser().parse_args(argv)

    try:
        result = seed_profile_memory(
            profile_id=args.profile,
            profiles_root=args.profiles_root,
            persist_dir=args.persist_dir,
            force=args.force,
        )
    except Exception as exc:
        print(f"FAILED: {exc}", file=err)
        return 1

    print(f"profile:        {result['profile_id']}", file=out)
    print(f"collection:     {result['collection']}", file=out)
    print(f"chunks_total:   {result['chunks_total']}", file=out)
    print(f"chunks_written: {result['chunks_written']}", file=out)
    if result["forced"]:
        print("(collection was reset before seeding)", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
