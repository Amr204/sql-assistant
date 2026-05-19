"""Runtime bundle exposed as ``app.state.agent`` when Vanna wiring succeeds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vanna.core.agent import Agent as VannaAgent

    from vai_agent.knowledge.profile_models import Profile
    from vai_agent.memory.memory_factory import AgentMemory
    from vai_agent.users import UserResolver
    from vai_agent.vanna_integration.policy_sql_runner import PolicySqlRunner


@dataclass
class VaiVannaRuntime:
    """Holds the live ``vanna`` :class:`~vanna.core.agent.agent.Agent` plus app context."""

    vanna: VannaAgent
    legacy_user_resolver: UserResolver
    profile: Profile
    chunk_memory: AgentMemory | None
    policy_runner: PolicySqlRunner
