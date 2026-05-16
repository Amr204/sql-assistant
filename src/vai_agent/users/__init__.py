"""User identity resolution (no authentication; trust comes from upstream)."""

from vai_agent.users.user_resolver import (
    User,
    UserResolutionError,
    UserResolver,
    UserResolverMode,
)

__all__ = ["User", "UserResolutionError", "UserResolver", "UserResolverMode"]
