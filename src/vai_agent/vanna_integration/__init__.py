"""Adapters and factories wiring this service to the ``vanna`` 2.x Agent API."""

from vai_agent.vanna_integration.factory import build_vanna_runtime
from vai_agent.vanna_integration.runtime import VaiVannaRuntime

__all__ = ["VaiVannaRuntime", "build_vanna_runtime"]
