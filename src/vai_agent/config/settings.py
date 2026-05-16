"""Application settings.

Settings are loaded from environment variables (and a local ``.env`` file
when present). Values are validated by Pydantic v2 ``BaseSettings``.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Deployment environment."""

    dev = "dev"
    staging = "staging"
    prod = "prod"


class LlmProvider(StrEnum):
    """Which LLM backend to instantiate (none = disable remote calls)."""

    none = "none"
    openrouter = "openrouter"


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

    context_max_tokens: int = Field(
        default=4_000,
        ge=256,
        le=128_000,
        description="Maximum estimated tokens for LLM context built by the context enhancer.",
    )
    db_profile_id: str = Field(
        default="dbnwind",
        description="Profile directory name under profiles_root.",
    )
    profiles_root: str = Field(
        default="profiles",
        description="Root directory containing profile subdirectories.",
    )
    chroma_persist_dir: str = Field(
        default=".data/chroma",
        description="Persistent directory for ChromaDB collections.",
    )
    vanna_file_storage_dir: str = Field(
        default=".data/vanna_files",
        description=(
            "Root directory for Vanna RunSqlTool CSV exports (LocalFileSystem); "
            "per-user subfolders are created under this path — never the project root."
        ),
    )
    user_resolver_mode: Literal["dev", "header", "future_oidc"] = Field(
        default="dev",
        description="User identity resolver mode.",
    )
    dev_user_id: str = Field(
        default="dev-user",
        description="Fallback user id used in dev resolver mode.",
    )
    dev_user_email: str | None = Field(
        default="dev@example.local",
        description="Fallback user email used in dev resolver mode.",
    )
    dev_user_groups: str = Field(
        default="analyst",
        description="Comma-separated groups used in dev resolver mode.",
    )

    llm_provider: LlmProvider = Field(
        default=LlmProvider.none,
        description="LLM vendor; 'none' skips building a remote chat client at startup.",
    )
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        description="Bearer token for OpenRouter (never log this value).",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Root URL for OpenAI-compatible endpoints (scheme + host + /api/v1).",
    )
    openrouter_model: str = Field(
        default="",
        description='Model slug, e.g. "openai/gpt-4o-mini" on OpenRouter.',
    )
    openrouter_http_referer: str | None = Field(
        default=None,
        description="Optional HTTP-Referer header recommended by OpenRouter for rankings.",
    )
    llm_http_timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=600.0,
        description="Wall-clock HTTP timeout for a single completion request.",
    )
    rate_limit_per_user_per_minute: int = Field(
        default=120,
        ge=1,
        le=10_000,
        description="Maximum requests per resolved user id per sliding minute window.",
    )
    rate_limit_per_ip_per_minute: int = Field(
        default=240,
        ge=1,
        le=100_000,
        description="Maximum requests per client IP per sliding minute window.",
    )
    rate_limit_per_group_per_minute: int = Field(
        default=500,
        ge=1,
        le=100_000,
        description="Maximum requests per declared access group per sliding minute window.",
    )
    rate_limit_per_user_per_day: int = Field(
        default=2_000,
        ge=1,
        le=1_000_000,
        description="Maximum requests per user id per rolling 24h window.",
    )
    rate_limit_max_concurrent_per_user: int = Field(
        default=5,
        ge=1,
        le=1_000,
        description="Maximum in-flight tool invocations per user id.",
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
