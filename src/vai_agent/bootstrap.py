"""Application factory.

Building the FastAPI app through a factory keeps wiring explicit and lets
tests construct fresh instances with overridden settings.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import chromadb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vai_agent import __version__
from vai_agent.api.health import router as health_router
from vai_agent.api.query import router as agent_router
from vai_agent.api.v1 import router as api_v1_router
from vai_agent.config.logging_config import configure_logging
from vai_agent.config.settings import Settings, get_settings
from vai_agent.db.connection import get_connection_settings
from vai_agent.knowledge import ProfileLoader
from vai_agent.memory import create_memory
from vai_agent.memory.chunking import ChunkingStrategy, chunk_profile
from vai_agent.memory.memory_factory import build_embedding_function
from vai_agent.vanna_integration.factory import build_vanna_runtime
from vai_agent.web.serving import register_web_routes

logger = logging.getLogger(__name__)


def _cors_origins(settings: Settings) -> list[str]:
    """Resolve allowed browser origins for the current environment."""

    origins: list[str] = []
    if settings.is_dev:
        origins.extend([
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ])
    for origin in settings.cors_origin_list():
        if origin not in origins:
            origins.append(origin)
    return origins


def setup_cors(app: FastAPI, settings: Settings) -> None:
    """Setup cors."""
    origins = _cors_origins(settings)
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-User-Id",
            "X-User-Email",
            "X-User-Groups",
        ],
    )


async def _shutdown_runtime(app: FastAPI) -> None:
    """Release shared HTTP and database resources."""

    from vai_agent.sqlfast.sql_generator import close_sql_generator_client

    await close_sql_generator_client()
    runtime = getattr(app.state, "agent", None)
    if runtime is not None:
        runtime.policy_runner._runner.close()
        logger.info("database connection pool closed")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await _shutdown_runtime(app)


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
    embedding_fn = build_embedding_function(embedding_device=settings.embedding_device)
    try:
        memory, chroma_client = create_memory(
            profile_id=settings.db_profile_id,
            persist_dir=settings.chroma_persist_dir,
            embedding_function=embedding_fn,
            embedding_device=settings.embedding_device,
        )
        app.state.memory = memory
        app.state.memory_client = chroma_client
        app.state.readiness["memory_ready"] = True
        if settings.warmup_on_startup:
            try:
                memory.search("__warmup__", n_results=1)
                logger.info("embedding model warmed up successfully")
            except Exception as exc:
                logger.warning("embedding warmup failed (non-fatal)", extra={"error": str(exc)})
        if memory.count() == 0 and app.state.profile is not None:
            try:
                strategy = ChunkingStrategy(settings.chunking_strategy)
            except ValueError:
                strategy = ChunkingStrategy.EARLY
            memory.seed(chunk_profile(app.state.profile, strategy=strategy))
            logger.info("auto-seeded memory for profile %s", settings.db_profile_id)
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

    if chroma_client is None:
        raise RuntimeError("ChromaDB client initialization failed — cannot proceed")

    try:
        connection_settings = get_connection_settings()
        runtime = build_vanna_runtime(
            profile=app.state.profile,
            connection_settings=connection_settings,
            settings=settings,
            chunk_memory=app.state.memory,
            chroma_client=chroma_client,
            vanna_embedding_function=embedding_fn,
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

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url="/redoc" if not settings.is_prod else None,
        lifespan=_lifespan,
    )

    setup_cors(app, settings)

    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(api_v1_router)

    register_web_routes(app, web_dist_dir="web/dist")

    _initialise_runtime(app, settings)

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
