"""Application factory.

Building the FastAPI app through a factory keeps wiring explicit and lets
tests construct fresh instances with overridden settings.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI

from vai_agent import __version__
from vai_agent.api.health import router as health_router
from vai_agent.api.query import router as agent_router
from vai_agent.config.logging_config import configure_logging
from vai_agent.config.settings import Settings, get_settings
from vai_agent.db.connection import get_connection_settings
from vai_agent.knowledge import ProfileLoader
from vai_agent.llm import build_chat_completion_client
from vai_agent.memory import create_memory
from vai_agent.users import User, UserResolver
from vai_agent.vai_app import build_agent

logger = logging.getLogger(__name__)


def _parse_dev_groups(raw: str) -> tuple[str, ...]:
    return tuple(g.strip() for g in raw.split(",") if g.strip())


def _build_user_resolver(settings: Settings) -> UserResolver:
    if settings.user_resolver_mode == "dev":
        return UserResolver(
            "dev",
            default_user=User(
                id=settings.dev_user_id,
                email=settings.dev_user_email,
                groups=_parse_dev_groups(settings.dev_user_groups),
            ),
        )
    return UserResolver(settings.user_resolver_mode)


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
                f"profile {settings.db_profile_id!r} not found; fell back to {fallback_id!r}"
            )
        except Exception as fallback_exc:
            app.state.readiness["errors"].append(f"profile load failed: {exc}")
            app.state.readiness["errors"].append(f"fallback profile load failed: {fallback_exc}")
            return

    try:
        connection_settings = get_connection_settings()
        user_resolver = _build_user_resolver(settings)
        agent = build_agent(
            profile=app.state.profile,
            connection_settings=connection_settings,
            user_resolver=user_resolver,
        )
        app.state.agent = agent
        app.state.readiness["agent_ready"] = True
    except Exception as exc:
        app.state.readiness["errors"].append(f"agent init failed: {exc}")

    try:
        memory, client = create_memory(
            profile_id=settings.db_profile_id,
            persist_dir=settings.chroma_persist_dir,
        )
        app.state.memory = memory
        app.state.memory_client = client
        app.state.readiness["memory_ready"] = True
    except Exception as exc:
        app.state.readiness["errors"].append(f"memory init failed: {exc}")

    app.state.readiness["ready"] = (
        app.state.readiness["profile_ready"]
        and app.state.readiness["agent_ready"]
        and app.state.readiness["memory_ready"]
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    settings:
        Optional pre-built settings. When ``None``, the cached settings
        from :func:`vai_agent.config.settings.get_settings` are used.

    Startup wiring loads the configured profile, builds the DB-backed
    agent, opens memory (ChromaDB), and optionally attaches
    ``app.state.llm_service`` when OpenRouter is configured. Failures are
    captured in ``app.state.readiness`` and surfaced by ``GET /ready``.
    """

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

    _initialise_runtime(app, settings)
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
