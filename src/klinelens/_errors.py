"""Errors the API answers with, one class per kind."""
from __future__ import annotations

from typing import Any, Optional


class KlineLensError(Exception):
    """An answer that is not data. ``status`` is the HTTP status (None if the API was not reached)."""

    def __init__(self, status: Optional[int], message: str, headers: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers

    def __str__(self) -> str:
        return f"{self.status}: {self.message}" if self.status else self.message


class BadRequestError(KlineLensError):
    """400: a parameter is wrong; the message says which."""


class AuthError(KlineLensError):
    """401: no key, or not a valid one."""


class PlanError(KlineLensError):
    """403: outside your plan (more history, a smaller interval or another timeframe)."""


class NotFoundError(KlineLensError):
    """404: no such endpoint."""


class RateLimitError(KlineLensError):
    """429: today's requests are used up. It resets at 00:00 UTC."""


class ServiceError(KlineLensError):
    """5xx, or the API could not be reached. Retried before it is raised."""
