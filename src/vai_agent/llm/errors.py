"""Exceptions raised by LLM integrations."""


class LlmError(Exception):
    """Base class for LLM client failures."""


class LlmUpstreamError(LlmError):
    """The remote LLM endpoint returned an error or malformed response."""
