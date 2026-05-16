"""Group-aware PII column access helper."""

from __future__ import annotations

from vai_agent.knowledge.profile_models import SecurityPolicy
from vai_agent.security.pii_policy import can_access_sensitive_column


def test_pii_group_access_admin_allowed() -> None:
    policy = SecurityPolicy(pii_columns=["Customers.Email"])
    assert can_access_sensitive_column(
        column_name="Email",
        table_name="Customers",
        user_groups=["admin"],
        policy=policy,
    )


def test_pii_group_access_analyst_blocked() -> None:
    policy = SecurityPolicy(pii_columns=["Customers.Email"])
    assert not can_access_sensitive_column(
        column_name="Email",
        table_name="Customers",
        user_groups=["analyst"],
        policy=policy,
    )


def test_pii_group_access_pii_reader_allowed() -> None:
    policy = SecurityPolicy(pii_columns=["Customers.Email"])
    assert can_access_sensitive_column(
        column_name="Email",
        table_name="Customers",
        user_groups=["pii_reader"],
        policy=policy,
    )
