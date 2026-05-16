"""Application factory.

Building the FastAPI app through a factory keeps wiring explicit and lets
tests construct fresh instances with overridden settings.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from vai_agent import __version__
from vai_agent.api.health import router as health_router
from vai_agent.config.logging_config import configure_logging
from vai_agent.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    settings:
        Optional pre-built settings. When ``None``, the cached settings
        from :func:`vai_agent.config.settings.get_settings` are used.
    """

    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url="/redoc" if not settings.is_prod else None,
    )

    app.include_router(health_router)

    logger.info(
        "application initialised",
        extra={"app_env": settings.app_env.value, "app_version": __version__},
    )
    return app
