"""Security layer: SQL policy, PII protection, and ingress checks.

Import submodules explicitly, e.g. ``vai_agent.security.sql_policy``,
``vai_agent.security.prompt_injection``. This package initializer stays
empty so lightweight ingress filters do not load sqlglot or policy engines.
"""

__all__: list[str] = []
