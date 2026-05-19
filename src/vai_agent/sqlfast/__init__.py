"""SQL fast path: compact context + JSON SQL LLM, then policy + MSSQL (no Vanna agent loop)."""

from vai_agent.sqlfast.intent_router import ChatPath, route_intent
from vai_agent.sqlfast.service import SqlFastService

__all__ = ["ChatPath", "SqlFastService", "route_intent"]
