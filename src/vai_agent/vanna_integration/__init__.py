"""Vanna integration package.

This package contains the production Vanna runtime integration for SQL Assistant.

Keep this package initializer intentionally lightweight:
- do not import factory.py here
- do not import chromadb here
- do not import vanna here
- do not re-export build_vanna_runtime here

Import runtime builders explicitly from:
    vai_agent.vanna_integration.factory
"""

__all__: list[str] = []
