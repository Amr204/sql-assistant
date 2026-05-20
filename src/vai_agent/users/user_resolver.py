"""Resolve the calling user from request context.

Three modes, selectable via the ``USER_RESOLVER_MODE`` environment variable:

``dev``
    Returns a fixed user constructed from ``DEV_USER_*`` env vars.
    Groups are taken exactly from configuration (no automatic escalation).
    This mode is for local development only and must not run in production.

``header``
    Reads ``X-User-Id``, ``X-User-Email`` and ``X-User-Groups`` headers,
    populated by an upstream proxy / API gateway that has already
    authenticated the request.

    **Deployment requirement:** expose this API only behind a **trusted reverse
    proxy** that terminates user authentication, strips client-supplied identity
    headers, and sets ``X-User-*`` from verified claims. Do **not** enable header
    mode on an endpoint reachable directly from the public internet without that
    proxy layer.

    Privileged group names (``admin``, ``superadmin``, ``root``) are **stripped**
    in this mode because the application cannot verify the upstream's trust
    boundary on its own; privileged access must be granted via a verified
    identity provider (Phase-7+) — see :data:`_PROTECTED_GROUPS`.

``future_oidc``
    Placeholder for a future JWT / OIDC implementation. Currently raises
    :class:`NotImplementedError` so the mode can be wired in config
    without silently degrading to ``dev``.

The class is dependency-free: callers pass a mapping of headers
(case-insensitive) rather than a Flask / FastAPI ``Request`` object.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Resolved caller identity."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    email: str | None = None
    groups: tuple[str, ...] = Field(default_factory=tuple)


class UserResolverMode(StrEnum):
    """UserResolverMode."""
    dev = "dev"
    header = "header"
    future_oidc = "future_oidc"


class UserResolutionError(Exception):
    """Raised when the resolver cannot determine a user from the request."""


# Group names that must never be granted via untrusted header claims.
_PROTECTED_GROUPS: frozenset[str] = frozenset({"admin", "superadmin", "root"})


def _parse_groups(raw: str) -> tuple[str, ...]:
    return tuple(g.strip() for g in raw.split(",") if g.strip())


class UserResolver:
    """Identity resolver. Stateless and cheap to construct.

    Parameters
    ----------
    mode:
        One of :class:`UserResolverMode`.
    default_user:
        Required for ``dev`` mode. Ignored in the other modes.
    """

    def __init__(
        self,
        mode: UserResolverMode | str,
        *,
        default_user: User | None = None,
    ) -> None:
        self.mode = UserResolverMode(mode)
        if self.mode is UserResolverMode.dev and default_user is None:
            raise ValueError("dev mode requires a default_user")
        self._default_user = default_user

    def resolve(self, headers: Mapping[str, str] | None = None) -> User:
        """Return the :class:`User` for the current request."""
        headers = headers or {}
        if self.mode is UserResolverMode.dev:
            assert self._default_user is not None  # guaranteed by __init__
            return self._default_user
        if self.mode is UserResolverMode.header:
            return self._from_headers(headers)
        if self.mode is UserResolverMode.future_oidc:  # pragma: no cover - defensive
            raise NotImplementedError(
                "OIDC user resolution is reserved for a future phase."
            )
        raise UserResolutionError(f"unknown resolver mode: {self.mode!r}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_header(headers: Mapping[str, str], name: str) -> str | None:
        # Case-insensitive lookup so we work with both Starlette's mapping
        # and a plain dict.
        for key, value in headers.items():
            if key.lower() == name.lower():
                return value
        return None

    def _from_headers(self, headers: Mapping[str, str]) -> User:
        user_id = self._get_header(headers, "X-User-Id")
        if not user_id:
            raise UserResolutionError("X-User-Id header is required in header mode.")
        email = self._get_header(headers, "X-User-Email")
        groups_raw = self._get_header(headers, "X-User-Groups") or ""
        groups = _parse_groups(groups_raw)
        # Strip protected groups: header mode cannot grant privileged access.
        filtered = tuple(g for g in groups if g.lower() not in _PROTECTED_GROUPS)
        return User(id=user_id, email=email, groups=filtered)
