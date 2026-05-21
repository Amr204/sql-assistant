"""VAI context support package.

The current Vanna runtime only depends on context_enhancer from this package.
Legacy agent_factory/tool_registry are intentionally not re-exported here to
avoid import-time coupling and accidental dependency on removed legacy modules.
"""

from vai_agent.vai_app.context_enhancer import (
    ContextEnhancer,
    ContextEnhancerConfig,
    EnhancementResult,
)

__all__ = [
    "ContextEnhancer",
    "ContextEnhancerConfig",
    "EnhancementResult",
]
