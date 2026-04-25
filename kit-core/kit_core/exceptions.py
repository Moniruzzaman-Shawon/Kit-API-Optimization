from __future__ import annotations


class KitError(Exception):
    """Base exception for all Kit errors."""


class ConfigurationError(KitError):
    """Raised when configuration is invalid or missing."""


class ConnectionError(KitError):
    """Raised when a connection to an external service fails."""


class RateLimitExceeded(KitError):
    """Raised when a rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class CircuitOpen(KitError):
    """Raised when a circuit breaker is in the open state."""

    def __init__(self, service: str, message: str | None = None):
        super().__init__(message or f"Circuit breaker open for service: {service}")
        self.service = service


class IdempotencyConflict(KitError):
    """Raised when an idempotency key conflict is detected."""

    def __init__(self, key: str, message: str | None = None):
        super().__init__(message or f"Idempotency conflict for key: {key}")
        self.key = key


class PaymentError(KitError):
    """Raised when a payment operation fails."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        code: str | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.code = code


class MediaError(KitError):
    """Raised when a media operation fails."""


class WebhookVerificationError(KitError):
    """Raised when webhook signature verification fails."""
