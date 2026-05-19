from __future__ import annotations

from fastapi import APIRouter

from vai_agent.api.v1 import chat, memory, profile, status, tools

router = APIRouter(prefix="/api/v1", tags=["api-v1"])

router.include_router(status.router)
router.include_router(chat.router)
router.include_router(memory.router)
router.include_router(profile.router)
router.include_router(tools.router)
