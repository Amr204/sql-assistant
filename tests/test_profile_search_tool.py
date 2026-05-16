"""Tests for :class:`vai_agent.tools.ProfileSearchTool`."""

from __future__ import annotations

from pathlib import Path

import pytest

from vai_agent.knowledge import ProfileLoader
from vai_agent.tools.profile_search_tool import ProfileSearchArgs, ProfileSearchTool
from vai_agent.users import User

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "profiles"


@pytest.fixture(scope="module")
def sample_profile():
    return ProfileLoader(FIXTURE_ROOT).load("sample")


@pytest.fixture()
def tool(sample_profile):
    return ProfileSearchTool(sample_profile)


@pytest.fixture()
def user():
    return User(id="u")


def _sources(result) -> set[str]:
    return {h["source"] for h in result.data["hits"]}


class TestSearch:
    def test_finds_glossary_term(self, tool, user):
        result = tool.execute(ProfileSearchArgs(query="customer"), user)
        assert result.success
        assert "glossary" in _sources(result)

    def test_arabic_query_matches(self, tool, user):
        result = tool.execute(ProfileSearchArgs(query="عميل"), user)
        assert result.success
        assert result.data["total_hits"] > 0

    def test_finds_column(self, tool, user):
        result = tool.execute(ProfileSearchArgs(query="CompanyName"), user)
        assert "column" in _sources(result)

    def test_finds_metric(self, tool, user):
        result = tool.execute(ProfileSearchArgs(query="revenue"), user)
        assert "metric" in _sources(result)

    def test_finds_table_profile(self, tool, user):
        result = tool.execute(ProfileSearchArgs(query="order line items"), user)
        # Either matches the schema description (table) or the per-table grain
        sources = _sources(result)
        assert sources & {"table", "table_profile"}

    def test_no_hits(self, tool, user):
        result = tool.execute(ProfileSearchArgs(query="zzz-nothing-matches-zzz"), user)
        assert result.success
        assert result.data["total_hits"] == 0
        assert result.data["hits"] == []

    def test_case_insensitive(self, tool, user):
        a = tool.execute(ProfileSearchArgs(query="CUSTOMER"), user)
        b = tool.execute(ProfileSearchArgs(query="customer"), user)
        assert a.data["total_hits"] == b.data["total_hits"]

    def test_limit_applied(self, tool, user):
        # 'c' is in many fields — limit to 3 and verify
        result = tool.execute(ProfileSearchArgs(query="c", limit=3), user)
        assert len(result.data["hits"]) <= 3

    def test_invalid_args_caught_at_construction(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProfileSearchArgs(query="")  # min_length=1 violated
