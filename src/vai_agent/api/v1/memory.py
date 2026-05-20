"""ChromaDB collection stats for diagnostics (memory + Vanna agent collections)."""

from __future__ import annotations

import re
from pathlib import Path

import chromadb
from fastapi import APIRouter, Request

from vai_agent.api.deps import require_runtime
from vai_agent.config.settings import get_settings

router = APIRouter(prefix="/memory", tags=["memory"])

_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_token(profile_id: str) -> str:
    s = _SAFE.sub("_", profile_id.strip())
    return s[:60] if len(s) > 60 else s


@router.get("", summary="Chroma memory collection counts")
async def memory_stats(request: Request) -> dict[str, object]:
    """Memory stats."""
    runtime = require_runtime(request)
    settings = get_settings()
    persist = str(Path(settings.chroma_persist_dir).resolve())
    client = chromadb.PersistentClient(path=persist)
    profile_id = runtime.profile.meta.profile_id
    mem_name = f"memory_{profile_id.replace(' ', '_').replace('.', '_')}"
    agent_name = f"vanna_agent_{_safe_token(profile_id)}"

    collections = client.list_collections()
    out: list[dict[str, object]] = []
    for col in collections:
        name = col.name
        try:
            cnt = col.count()
            if cnt > 0:
                sample = col.get(limit=min(2, cnt))
                meta_sample = sample.get("metadatas")
            else:
                meta_sample = None
        except Exception as exc:  # pragma: no cover - defensive
            cnt = -1
            meta_sample = [str(exc)]
        out.append(
            {
                "name": name,
                "count": cnt,
                "sample_metadata": meta_sample,
            },
        )

    mem_count = next((x["count"] for x in out if x["name"] == mem_name), None)
    agent_count = next((x["count"] for x in out if x["name"] == agent_name), None)

    return {
        "persist_directory": persist,
        "profile_id": profile_id,
        "memory_collection": mem_name,
        "memory_count": mem_count,
        "vanna_agent_collection": agent_name,
        "vanna_agent_count": agent_count,
        "memory_seeded": bool(mem_count and mem_count > 0),
        "collections": out,
    }
