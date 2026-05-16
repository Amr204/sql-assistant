"""Tests for :mod:`vai_agent.users.user_resolver`."""

from __future__ import annotations

import pytest

from vai_agent.users import (
    User,
    UserResolutionError,
    UserResolver,
    UserResolverMode,
)

# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class TestUser:
    def test_minimum_fields(self) -> None:
        u = User(id="abc")
        assert u.id == "abc"
        assert u.email is None
        assert u.groups == ()

    def test_groups_are_tuple(self) -> None:
        u = User(id="x", groups=("analyst", "reader"))
        assert isinstance(u.groups, tuple)

    def test_user_is_frozen(self) -> None:
        from pydantic import ValidationError
        u = User(id="x")
        with pytest.raises(ValidationError):
            u.id = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Dev mode
# ---------------------------------------------------------------------------


class TestDevMode:
    def test_returns_default_user(self) -> None:
        default = User(id="dev", email="dev@example.local", groups=("admin",))
        r = UserResolver(UserResolverMode.dev, default_user=default)
        assert r.resolve() == default

    def test_headers_are_ignored_in_dev_mode(self) -> None:
        default = User(id="dev", groups=("analyst",))
        r = UserResolver(UserResolverMode.dev, default_user=default)
        u = r.resolve({"X-User-Id": "imposter"})
        assert u.id == "dev"

    def test_dev_mode_requires_default_user(self) -> None:
        with pytest.raises(ValueError, match="default_user"):
            UserResolver(UserResolverMode.dev)

    def test_admin_group_allowed_in_dev(self) -> None:
        default = User(id="dev", groups=("admin",))
        r = UserResolver(UserResolverMode.dev, default_user=default)
        assert "admin" in r.resolve().groups


# ---------------------------------------------------------------------------
# Header mode
# ---------------------------------------------------------------------------


class TestHeaderMode:
    def _r(self) -> UserResolver:
        return UserResolver(UserResolverMode.header)

    def test_full_headers(self) -> None:
        u = self._r().resolve({
            "X-User-Id": "alice",
            "X-User-Email": "alice@example.com",
            "X-User-Groups": "analyst,reader",
        })
        assert u.id == "alice"
        assert u.email == "alice@example.com"
        assert u.groups == ("analyst", "reader")

    def test_case_insensitive_header_names(self) -> None:
        u = self._r().resolve({
            "x-user-id": "bob",
            "x-user-groups": "  analyst , reader ",
        })
        assert u.id == "bob"
        assert u.groups == ("analyst", "reader")

    def test_missing_user_id_raises(self) -> None:
        with pytest.raises(UserResolutionError):
            self._r().resolve({"X-User-Email": "x@y.z"})

    def test_admin_group_is_stripped(self) -> None:
        u = self._r().resolve({
            "X-User-Id": "evil",
            "X-User-Groups": "admin,analyst",
        })
        assert "admin" not in u.groups
        assert "analyst" in u.groups

    def test_superadmin_and_root_stripped(self) -> None:
        u = self._r().resolve({
            "X-User-Id": "x",
            "X-User-Groups": "superadmin,root,reader",
        })
        assert u.groups == ("reader",)

    def test_empty_groups_header(self) -> None:
        u = self._r().resolve({"X-User-Id": "x", "X-User-Groups": ""})
        assert u.groups == ()

    def test_no_groups_header(self) -> None:
        u = self._r().resolve({"X-User-Id": "x"})
        assert u.groups == ()


# ---------------------------------------------------------------------------
# future_oidc mode
# ---------------------------------------------------------------------------


class TestFutureOidc:
    def test_raises_not_implemented(self) -> None:
        r = UserResolver(UserResolverMode.future_oidc)
        with pytest.raises(NotImplementedError):
            r.resolve({"Authorization": "Bearer xyz"})
