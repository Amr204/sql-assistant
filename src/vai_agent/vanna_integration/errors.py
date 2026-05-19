"""Exceptions raised when Vanna SQL tools reject or abort execution."""

from __future__ import annotations


class QueryRejectedError(Exception):
    """Base class for query rejections surfaced to tools and the LLM."""

    def __init__(self, message: str, *, error_code: str = "rejected") -> None:
        super().__init__(message)
        self.error_code = error_code


class PolicyRejectedError(QueryRejectedError):
    """Query blocked by SQL or data-protection policy."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="policy")


class SqlRunnerTimeoutError(QueryRejectedError):
    """Query exceeded the configured database time limit."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="timeout")


class RequestCancelledError(QueryRejectedError):
    """The client or upstream handler cancelled the request."""

    def __init__(self, message: str = "Request was cancelled by the user.") -> None:
        super().__init__(message, error_code="cancelled")
