"""Application settings.

Settings are loaded from environment variables (and a local ``.env`` file
when present). Values are validated by Pydantic v2 ``BaseSettings``.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Deployment environment."""

    dev = "dev"
    staging = "staging"
    prod = "prod"


class LlmProvider(StrEnum):
    """Which LLM backend to instantiate (none = disable remote calls)."""

    none = "none"
    openai_compatible = "openai_compatible"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["text", "json"]

_DEFAULT_MODEL_BASE_URL = "https://openrouter.ai/api/v1"


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
    log_dir: str = Field(default="logs", description="Directory for application log files.")
    log_file: str = Field(default="app.log", description="Application log filename (text or JSON lines).")

    enable_sql_csv_exports: bool = Field(
        default=False,
        description="When false, RunSqlTool does not receive a file sink (no query_results CSV).",
    )
    enable_visualization_tools: bool = Field(
        default=False,
        description="Reserved: when false, prompts discourage chart/visualization tool use.",
    )
    sql_auto_export_min_rows: int = Field(
        default=1000,
        ge=1,
        description="Minimum rows before auto CSV export would apply (reserved for future use).",
    )

    audit_enabled: bool = Field(default=True, description="Write activity audit rows to Excel.")
    audit_dir: str = Field(default="audit", description="Directory for activity audit workbook.")
    audit_file: str = Field(
        default="activity_log.xlsx",
        description="Excel filename for activity audit.",
    )

    context_max_tokens: int = Field(
        default=2_500,
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
        description=(
            "Comma-separated groups used in dev resolver mode. "
            "Set explicitly (e.g. admin) for local privileged testing."
        ),
    )

    cors_origins: str = Field(
        default="",
        description=(
            "Comma-separated allowed browser origins for CORS. "
            "In dev, localhost:5173 is always included. "
            "In staging/prod, set explicit origins (no wildcard)."
        ),
    )

    sql_fast_path_enabled: bool = Field(
        default=True,
        description="When true, clear data questions may use the SQL fast path before the Vanna agent.",
    )
    agent_memory_auto_save: bool = Field(
        default=True,
        description="When true, successful SQL fast-path runs are saved to Chroma agent memory.",
    )

    model_provider: LlmProvider = Field(
        default=LlmProvider.none,
        description="Model vendor; 'none' skips building a remote chat client at startup.",
        validation_alias=AliasChoices("MODEL_PROVIDER", "LLM_PROVIDER"),
    )
    model_api_key: SecretStr | None = Field(
        default=None,
        description="Bearer token for the OpenAI-compatible API (never log this value).",
        validation_alias=AliasChoices("MODEL_API_KEY", "OPENROUTER_API_KEY"),
    )
    model_base_url: str = Field(
        default=_DEFAULT_MODEL_BASE_URL,
        description="Root URL for OpenAI-compatible chat completions (scheme + host + /v1).",
        validation_alias=AliasChoices("MODEL_BASE_URL", "OPENROUTER_BASE_URL"),
    )
    model_name: str = Field(
        default="",
        description='Model slug, e.g. "openai/gpt-4o-mini" or a local server model id.',
        validation_alias=AliasChoices("MODEL_NAME", "OPENROUTER_MODEL"),
    )
    model_http_referer: str | None = Field(
        default=None,
        description="Optional HTTP-Referer header for providers that use it (e.g. OpenRouter).",
        validation_alias=AliasChoices("MODEL_HTTP_REFERER", "OPENROUTER_HTTP_REFERER"),
    )
    model_http_timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=600.0,
        description="Wall-clock HTTP timeout for a single completion request.",
        validation_alias=AliasChoices("MODEL_HTTP_TIMEOUT_SECONDS", "LLM_HTTP_TIMEOUT_SECONDS"),
    )
    model_fallback_name: str = Field(
        default="",
        description="Fallback model slug when the primary model fails after retries.",
        validation_alias=AliasChoices("MODEL_FALLBACK_NAME", "OPENROUTER_FALLBACK_MODEL"),
    )

    embedding_device: str = Field(
        default="cpu",
        description=(
            "Device for paraphrase-multilingual-MiniLM-L12-v2 embeddings: 'cpu' or 'cuda'."
        ),
    )
    chunking_strategy: str = Field(
        default="early",
        description="Profile chunking: 'early' (chunk then embed) or 'late' (embed then chunk).",
    )
    warmup_on_startup: bool = Field(
        default=True,
        description="Run a dummy vector search at startup to load the embedding model.",
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

    @field_validator("model_provider", mode="before")
    @classmethod
    def _coerce_model_provider(cls, v: object) -> object:
        if v == "openrouter":
            return LlmProvider.openai_compatible
        return v

    @model_validator(mode="after")
    def _validate_deployment_security(self) -> Self:
        """Reject unsafe resolver/CORS combinations for non-dev environments."""

        if self.app_env is not AppEnv.dev and self.user_resolver_mode == "dev":
            raise ValueError(
                "USER_RESOLVER_MODE=dev is only permitted when APP_ENV=dev. "
                "Use header (behind a trusted proxy) or future_oidc in staging/prod."
            )
        if self.is_prod:
            for origin in self.cors_origin_list():
                if origin.strip() == "*":
                    raise ValueError("CORS_ORIGINS must not use wildcard (*) in production.")
        return self

    @model_validator(mode="before")
    @classmethod
    def _normalize_model_env(cls, data: Any) -> Any:
        """Map deprecated env/kwargs; prefer ``MODEL_*`` over ``OPENROUTER_*``."""

        if not isinstance(data, dict):
            return data
        merged = dict(data)

        if "llm_provider" in merged and "model_provider" not in merged:
            merged["model_provider"] = merged.pop("llm_provider")

        prov = merged.get("model_provider")
        if prov == "openrouter":
            merged["model_provider"] = LlmProvider.openai_compatible

        def _env(name: str) -> str | None:
            val = os.environ.get(name) or os.environ.get(name.lower())
            if val is not None and str(val).strip():
                return str(val).strip()
            return None

        def _prefer(field: str, primary_env: str, legacy_env: str) -> None:
            primary = _env(primary_env)
            legacy = _env(legacy_env)
            if primary:
                merged[field] = primary
            elif legacy and field not in merged:
                merged[field] = legacy

        _prefer("model_api_key", "MODEL_API_KEY", "OPENROUTER_API_KEY")
        _prefer("model_name", "MODEL_NAME", "OPENROUTER_MODEL")
        _prefer("model_base_url", "MODEL_BASE_URL", "OPENROUTER_BASE_URL")
        _prefer("model_http_referer", "MODEL_HTTP_REFERER", "OPENROUTER_HTTP_REFERER")
        _prefer("model_http_timeout_seconds", "MODEL_HTTP_TIMEOUT_SECONDS", "LLM_HTTP_TIMEOUT_SECONDS")

        prov_env = _env("MODEL_PROVIDER") or _env("LLM_PROVIDER")
        if prov_env:
            merged["model_provider"] = (
                LlmProvider.openai_compatible if prov_env == "openrouter" else prov_env
            )

        return merged

    @property
    def llm_provider(self) -> LlmProvider:
        """Deprecated alias for :attr:`model_provider`."""

        return self.model_provider

    @property
    def effective_model_api_key(self) -> SecretStr | None:
        """Effective model api key."""
        return self.model_api_key

    @property
    def effective_model_name(self) -> str:
        """Effective model name."""
        return self.model_name.strip()

    @property
    def effective_model_base_url(self) -> str:
        """Effective model base url."""
        base = self.model_base_url.strip()
        return base or _DEFAULT_MODEL_BASE_URL

    @property
    def effective_model_http_referer(self) -> str | None:
        """Effective model http referer."""
        ref = (self.model_http_referer or "").strip()
        return ref or None

    @property
    def audit_model_provider(self) -> str:
        """Label for activity audit (only names OpenRouter when that host is configured)."""

        if "openrouter.ai" in self.effective_model_base_url.lower():
            return "openrouter"
        return self.model_provider.value

    @property
    def is_dev(self) -> bool:
        """Return True when dev."""
        return self.app_env is AppEnv.dev

    @property
    def is_prod(self) -> bool:
        """Return True when prod."""
        return self.app_env is AppEnv.prod

    def cors_origin_list(self) -> list[str]:
        """Parse :attr:`cors_origins` into a de-duplicated list."""

        seen: set[str] = set()
        out: list[str] = []
        for part in self.cors_origins.split(","):
            origin = part.strip()
            if origin and origin not in seen:
                seen.add(origin)
                out.append(origin)
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` instance for this process."""

    return Settings()
