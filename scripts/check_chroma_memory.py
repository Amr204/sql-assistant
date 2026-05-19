#!/usr/bin/env python3
"""Print ChromaDB collection stats (memory_<profile> + vanna_agent_<profile>)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import chromadb  # noqa: E402

_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def safe_token(profile_id: str) -> str:
    s = _SAFE.sub("_", profile_id.strip())
    return s[:60] if len(s) > 60 else s


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--persist-dir",
        default=os.environ.get("CHROMA_PERSIST_DIR", ".data/chroma"),
        help="Chroma persist directory (default: env CHROMA_PERSIST_DIR or .data/chroma)",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("DB_PROFILE_ID", "dbnwind"),
        help="Profile id for expected collection names (default: env DB_PROFILE_ID or dbnwind)",
    )
    args = parser.parse_args()

    persist = str(Path(args.persist_dir).resolve())
    client = chromadb.PersistentClient(path=persist)
    profile = args.profile
    mem_name = f"memory_{profile.replace(' ', '_').replace('.', '_')}"
    agent_name = f"vanna_agent_{safe_token(profile)}"

    names = [c.name for c in client.list_collections()]
    print(f"persist_directory={persist}")
    print(f"profile_id={profile}")
    print(f"expected memory collection={mem_name}")
    print(f"expected vanna agent collection={agent_name}")
    print("--- collections ---")

    mem_count = None
    agent_count = None
    for name in sorted(names):
        col = client.get_collection(name)
        cnt = col.count()
        meta_sample = None
        if cnt:
            g = col.get(limit=min(3, cnt))
            meta_sample = g.get("metadatas")
        print(f"{name}\tcount={cnt}\tsample_metadata={json.dumps(meta_sample, default=str)[:500]}")
        if name == mem_name:
            mem_count = cnt
        if name == agent_name:
            agent_count = cnt

    print("--- summary ---")
    print(f"memory_seeded={bool(mem_count and mem_count > 0)} (memory_{profile} count={mem_count})")
    print(
        f"vanna_agent_grows_after_fast_path_queries="
        f"(check vanna_agent_{safe_token(profile)} count={agent_count} before/after)",
    )


if __name__ == "__main__":
    main()
