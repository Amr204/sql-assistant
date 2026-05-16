"""Tests for :class:`vai_agent.vai_app.tool_registry.ToolRegistry`."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from vai_agent.tools.base import ToolBase
from vai_agent.users import User
from vai_agent.vai_app.tool_registry import ToolRegistry


class _Args(BaseModel):
    pass


def _tool(name: str, *, access_groups: tuple[str, ...] = ()) -> ToolBase:
    # Build a concrete subclass with all abstract methods implemented so
    # ABC instantiation succeeds. Each call returns a fresh class.
    cls = type(
        f"_Tool_{name}",
        (ToolBase,),
        {
            "name": name,
            "description": "test",
            "args_model": _Args,
            "access_groups": access_groups,
            "execute": lambda self, args, user: self._ok({}),
        },
    )
    return cls()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_and_get(self) -> None:
        r = ToolRegistry()
        t = _tool("alpha")
        r.register(t)
        assert r.get("alpha") is t

    def test_duplicate_registration_raises(self) -> None:
        r = ToolRegistry()
        r.register(_tool("alpha"))
        with pytest.raises(ValueError, match="alpha"):
            r.register(_tool("alpha"))

    def test_unknown_tool_returns_none(self) -> None:
        assert ToolRegistry().get("nope") is None

    def test_contains_and_len(self) -> None:
        r = ToolRegistry()
        assert "x" not in r
        assert len(r) == 0
        r.register(_tool("x"))
        assert "x" in r
        assert len(r) == 1

    def test_register_all(self) -> None:
        r = ToolRegistry()
        r.register_all([_tool("a"), _tool("b")])
        assert sorted(r.names()) == ["a", "b"]


# ---------------------------------------------------------------------------
# Access-group filtering
# ---------------------------------------------------------------------------


class TestAccessControl:
    def test_empty_access_groups_open_to_all(self) -> None:
        r = ToolRegistry()
        r.register(_tool("open"))
        assert r.user_can_use(r.get("open"), User(id="x")) is True

    def test_user_with_matching_group_allowed(self) -> None:
        r = ToolRegistry()
        r.register(_tool("private", access_groups=("admin",)))
        assert r.user_can_use(r.get("private"), User(id="x", groups=("admin",))) is True

    def test_user_without_group_denied(self) -> None:
        r = ToolRegistry()
        r.register(_tool("private", access_groups=("admin",)))
        assert r.user_can_use(r.get("private"), User(id="x", groups=("reader",))) is False

    def test_match_is_case_insensitive(self) -> None:
        r = ToolRegistry()
        r.register(_tool("p", access_groups=("Admin",)))
        assert r.user_can_use(r.get("p"), User(id="x", groups=("ADMIN",))) is True

    def test_list_for_user_filters_correctly(self) -> None:
        r = ToolRegistry()
        r.register_all([
            _tool("open"),
            _tool("admin_only", access_groups=("admin",)),
            _tool("analyst_only", access_groups=("analyst",)),
        ])
        u = User(id="x", groups=("analyst",))
        names = {t.name for t in r.list_for_user(u)}
        assert names == {"open", "analyst_only"}
