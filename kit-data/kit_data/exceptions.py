"""Exceptions raised by kit-data, extending the shared kit-core hierarchy."""

from __future__ import annotations

from kit_core.exceptions import KitError


class ConcurrencyLimitExceeded(KitError):
    """Raised when a ConcurrencyLimiter has no free slots."""

    def __init__(self, name: str, limit: int, message: str | None = None) -> None:
        super().__init__(message or f"Concurrency limit reached for '{name}' (max {limit})")
        self.name = name
        self.limit = limit


class NoHealthyReplicas(KitError):
    """Raised when a ReplicaRouter has no healthy replicas to route to."""
