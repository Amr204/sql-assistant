"""Application settings.

Settings are loaded from environment variables (and a local ``.env`` file
when present). Values are validated by Pydantic v2 ``BaseSettings``.

Only Phase 1 keys are modelled here. Additional groups (LLM, DB, memory,
security) will be added in their own settings sub-models as later phases
introduce them, to keep this module focused and reviewable.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Deployment environment."""

    dev = "dev"
    staging = "staging"
    prod = "prod"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["text", "json"]


class Settings(BaseSettings):
    """Top-level application settings.

    Loaded once per process via :func:`get_settings` (LRU-cached).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="sql-assistant", description="Display name of the service.")
    app_version: str = Field(default="0.1.0", description="Semantic version of the service.")
    app_env: AppEnv = Field(default=AppEnv.dev, description="Deployment environment.")
    app_host: str = Field(default="127.0.0.1", description="Bind host for the HTTP server.")
    app_port: int = Field(default=8000, ge=1, le=65535, description="Bind port for the HTTP server.")

    log_level: LogLevel = Field(default="INFO", description="Root logger level.")
    log_format: LogFormat = Field(
        default="text",
        description="Log formatter: 'text' for human-readable, 'json' for structured logs.",
    )

    @property
    def is_dev(self) -> bool:
        return self.app_env is AppEnv.dev

    @property
    def is_prod(self) -> bool:
        return self.app_env is AppEnv.prod


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` instance for this process."""

    return Settings()
