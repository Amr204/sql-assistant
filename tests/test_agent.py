"""Tests for :class:`vai_agent.vai_app.agent_factory.Agent`."""

from __future__ import annotations

from pydantic import BaseModel

from vai_agent.tools.base import ToolBase, ToolResult
from vai_agent.users import User, UserResolver, UserResolverMode
from vai_agent.vai_app.agent_factory import Agent
from vai_agent.vai_app.tool_registry import ToolRegistry


class _PingArgs(BaseModel):
    msg: str


class _PingTool(ToolBase):
    name = "ping"
    description = "Echo back the message."
    args_model = _PingArgs

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        assert isinstance(args, _PingArgs)
        return self._ok({"msg": args.msg})


class _AdminTool(ToolBase):
    name = "admin_only"
    description = "Privileged."
    args_model = _PingArgs
    access_groups = ("admin",)

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        return self._ok({"ok": True})


class _BrokenTool(ToolBase):
    name = "broken"
    description = "Always raises."
    args_model = _PingArgs

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        raise RuntimeError("oops")


def _agent(*tools: ToolBase, mode: UserResolverMode = UserResolverMode.dev) -> Agent:
    registry = ToolRegistry()
    registry.register_all(tools)
    resolver = UserResolver(
        mode, default_user=User(id="dev", groups=("analyst",)) if mode is UserResolverMode.dev else None,
    )
    return Agent(registry, resolver)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestInvoke:
    def test_unknown_tool(self) -> None:
        agent = _agent()
        r = agent.invoke("ghost", {}, User(id="u"))
        assert not r.success
        assert "Unknown tool" in r.error
        assert "request_id" in r.metadata

    def test_happy_path(self) -> None:
        agent = _agent(_PingTool())
        r = agent.invoke("ping", {"msg": "hi"}, User(id="u"))
        assert r.success
        assert r.data == {"msg": "hi"}
        assert "request_id" in r.metadata

    def test_request_id_is_set_when_not_provided(self) -> None:
        agent = _agent(_PingTool())
        r = agent.invoke("ping", {"msg": "x"}, User(id="u"))
        assert r.metadata["request_id"]

    def test_request_id_passthrough(self) -> None:
        agent = _agent(_PingTool())
        r = agent.invoke("ping", {"msg": "x"}, User(id="u"), request_id="explicit-rid")
        assert r.metadata["request_id"] == "explicit-rid"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestArgValidation:
    def test_invalid_args_returns_failure(self) -> None:
        agent = _agent(_PingTool())
        r = agent.invoke("ping", {"wrong": "field"}, User(id="u"))
        assert not r.success
        assert "Invalid arguments" in r.error
        assert "validation_errors" in r.metadata


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


class TestAccess:
    def test_user_without_group_is_denied(self) -> None:
        agent = _agent(_AdminTool())
        r = agent.invoke("admin_only", {"msg": "x"}, User(id="u", groups=("reader",)))
        assert not r.success
        assert "Access denied" in r.error

    def test_user_with_group_passes(self) -> None:
        agent = _agent(_AdminTool())
        r = agent.invoke("admin_only", {"msg": "x"}, User(id="u", groups=("admin",)))
        assert r.success


# ---------------------------------------------------------------------------
# Unhandled tool exceptions
# ---------------------------------------------------------------------------


class TestExceptionGuard:
    def test_unhandled_tool_exception_does_not_leak(self) -> None:
        agent = _agent(_BrokenTool())
        r = agent.invoke("broken", {"msg": "x"}, User(id="u"))
        assert not r.success
        assert "Internal error" in r.error
        # The exception message must not be in either field
        assert "oops" not in (r.error or "")
        assert "oops" not in str(r.metadata)
        # But the exception type IS allowed (operator hint)
        assert r.metadata["exc_type"] == "RuntimeError"
