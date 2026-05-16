"""Application factory.

Building the FastAPI app through a factory keeps wiring explicit and lets
tests construct fresh instances with overridden settings.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import chromadb
from fastapi import FastAPI

from vai_agent import __version__
from vai_agent.api.chat import router as chat_router
from vai_agent.api.health import router as health_router
from vai_agent.api.query import router as agent_router
from vai_agent.config.logging_config import configure_logging
from vai_agent.config.settings import Settings, get_settings
from vai_agent.db.connection import get_connection_settings
from vai_agent.knowledge import ProfileLoader
from vai_agent.llm.factory import build_chat_completion_client
from vai_agent.memory import create_memory
from vai_agent.vanna_integration.factory import build_vanna_runtime
from vai_agent.vanna_integration.runtime import VaiVannaRuntime

logger = logging.getLogger(__name__)


def _initialise_runtime(app: FastAPI, settings: Settings) -> None:
    app.state.agent = None
    app.state.profile = None
    app.state.memory = None
    app.state.memory_client = None
    app.state.readiness = {
        "ready": False,
        "profile_ready": False,
        "agent_ready": False,
        "memory_ready": False,
        "tools_ready": False,
        "llm_ready": False,
        "errors": [],
    }

    loader = ProfileLoader(Path(settings.profiles_root))
    try:
        profile = loader.load(settings.db_profile_id)
        app.state.profile = profile
        app.state.readiness["profile_ready"] = True
    except Exception as exc:
        fallback_id = "dbnwind"
        try:
            profile = loader.load(fallback_id)
            app.state.profile = profile
            app.state.readiness["profile_ready"] = True
            app.state.readiness["errors"].append(
                f"profile {settings.db_profile_id!r} not found; fell back to {fallback_id!r}",
            )
        except Exception as fallback_exc:
            app.state.readiness["errors"].append(f"profile load failed: {exc}")
            app.state.readiness["errors"].append(f"fallback profile load failed: {fallback_exc}")
            return

    chroma_client: chromadb.api.ClientAPI | None = None
    try:
        memory, chroma_client = create_memory(
            profile_id=settings.db_profile_id,
            persist_dir=settings.chroma_persist_dir,
        )
        app.state.memory = memory
        app.state.memory_client = chroma_client
        app.state.readiness["memory_ready"] = True
    except Exception as exc:
        app.state.readiness["errors"].append(f"memory init failed: {exc}")
        try:
            persist = Path(settings.chroma_persist_dir)
            persist.mkdir(parents=True, exist_ok=True)
            chroma_client = chromadb.PersistentClient(path=str(persist))
            app.state.memory_client = chroma_client
        except Exception as client_exc:
            app.state.readiness["errors"].append(f"chroma client fallback failed: {client_exc}")
            return

    assert chroma_client is not None

    try:
        connection_settings = get_connection_settings()
        runtime = build_vanna_runtime(
            profile=app.state.profile,
            connection_settings=connection_settings,
            settings=settings,
            chunk_memory=app.state.memory,
        )
        app.state.agent = runtime
        app.state.readiness["agent_ready"] = True
        app.state.readiness["tools_ready"] = True
        from vanna.integrations.mock import MockLlmService

        app.state.readiness["llm_ready"] = not isinstance(
            runtime.vanna.llm_service,
            MockLlmService,
        )
    except Exception as exc:
        app.state.readiness["errors"].append(f"agent init failed: {exc}")

    app.state.readiness["ready"] = (
        app.state.readiness["profile_ready"]
        and app.state.readiness["agent_ready"]
        and app.state.readiness["memory_ready"]
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the FastAPI application."""

    settings = settings or get_settings()
    configure_logging(settings)

    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        svc = getattr(app.state, "llm_service", None)
        if svc is None:
            return
        closer = getattr(svc, "close", None)
        if callable(closer):
            closer()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url="/redoc" if not settings.is_prod else None,
    )

    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(chat_router)

    _initialise_runtime(app, settings)

    runtime = getattr(app.state, "agent", None)
    if isinstance(runtime, VaiVannaRuntime):
        from vai_agent.vanna_integration.guarded_chat import GuardedChatHandler
        from vai_agent.vanna_integration.vanna_fastapi_routes import register_chat_routes

        register_chat_routes(
            app,
            GuardedChatHandler(runtime.vanna, settings),
            config={
                "dev_mode": settings.is_dev,
                "api_base_url": "",
            },
        )

    app.state.llm_service = build_chat_completion_client(settings)

    logger.info(
        "application initialised",
        extra={
            "app_env": settings.app_env.value,
            "app_version": __version__,
            "profile_id": settings.db_profile_id,
            "ready": app.state.readiness.get("ready", False),
        },
    )
    return app
