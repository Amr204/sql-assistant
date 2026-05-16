"""ASGI entry point.

Run with::

    uvicorn vai_agent.main:app --reload

The module-level ``app`` symbol is what ``uvicorn`` imports.
"""

from __future__ import annotations

from vai_agent.bootstrap import create_app

app = create_app()
