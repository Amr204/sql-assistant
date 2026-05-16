"""Bridge the app's synchronous :class:`~vai_agent.users.UserResolver` to Vanna's async API."""

from __future__ import annotations

import asyncio

from vanna.core.user import UserResolver
from vanna.core.user.models import User as VannaUser
from vanna.core.user.request_context import RequestContext

from vai_agent.users import UserResolver as LegacyUserResolver


class LegacyUserResolverBridge(UserResolver):
    """Wraps :class:`~vai_agent.users.UserResolver` for ``vanna.core.agent.Agent``."""

    def __init__(self, inner: LegacyUserResolver) -> None:
        self._inner = inner

    async def resolve_user(self, request_context: RequestContext) -> VannaUser:
        headers = {str(k): str(v) for k, v in request_context.headers.items()}

        def _resolve() -> object:
            return self._inner.resolve(headers)

        legacy = await asyncio.to_thread(_resolve)
        return VannaUser(
            id=legacy.id,
            email=legacy.email,
            username=legacy.id,
            group_memberships=list(legacy.groups),
            metadata={},
        )
