"""Tests for :mod:`vai_agent.tools.base`."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from vai_agent.tools.base import ToolBase, ToolResult
from vai_agent.users import User


class _Args(BaseModel):
    x: int


class _Echo(ToolBase):
    name = "echo"
    description = "Echo a number back."
    args_model = _Args

    def execute(self, args: BaseModel, user: User) -> ToolResult:
        assert isinstance(args, _Args)
        return self._ok({"x": args.x}, request_id="rid-1")


class TestToolBase:
    def test_ok_helper(self) -> None:
        tool = _Echo()
        result = tool.execute(_Args(x=42), User(id="u"))
        assert result.success is True
        assert result.tool == "echo"
        assert result.data == {"x": 42}
        assert result.metadata == {"request_id": "rid-1"}
        assert result.error is None

    def test_fail_helper(self) -> None:
        class _Bad(_Echo):
            name = "bad"
            def execute(self, args: BaseModel, user: User) -> ToolResult:
                return self._fail("something broke", reason="testing")

        result = _Bad().execute(_Args(x=1), User(id="u"))
        assert result.success is False
        assert result.error == "something broke"
        assert result.metadata == {"reason": "testing"}

    def test_default_access_groups_empty(self) -> None:
        assert _Echo.access_groups == ()

    def test_result_is_frozen(self) -> None:
        from pydantic import ValidationError
        r = ToolResult(success=True, tool="x")
        with pytest.raises(ValidationError):
            r.tool = "y"  # type: ignore[misc]
