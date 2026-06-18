"""Tests for kit_core.exceptions."""

from __future__ import annotations

import pytest
from kit_core.exceptions import (
    CircuitOpen,
    ConfigurationError,
    ConnectionError,
    IdempotencyConflict,
    KitError,
    MediaError,
    PaymentError,
    RateLimitExceeded,
    WebhookVerificationError,
)


class TestExceptionHierarchy:
    """All custom exceptions inherit from KitError."""

    @pytest.mark.parametrize(
        "exc_cls",
        [
            ConfigurationError,
            ConnectionError,
            RateLimitExceeded,
            CircuitOpen,
            MediaError,
            WebhookVerificationError,
        ],
    )
    def test_subclass_of_kit_error(self, exc_cls):
        assert issubclass(exc_cls, KitError)

    def test_kit_error_is_exception(self):
        assert issubclass(KitError, Exception)


class TestRateLimitExceeded:
    def test_default_message(self):
        exc = RateLimitExceeded()
        assert str(exc) == "Rate limit exceeded"
        assert exc.retry_after is None

    def test_custom_retry_after(self):
        exc = RateLimitExceeded("slow down", retry_after=30.0)
        assert exc.retry_after == 30.0
        assert "slow down" in str(exc)


class TestCircuitOpen:
    def test_default_message(self):
        exc = CircuitOpen("payments")
        assert "payments" in str(exc)
        assert exc.service == "payments"

    def test_custom_message(self):
        exc = CircuitOpen("api", message="custom msg")
        assert str(exc) == "custom msg"
        assert exc.service == "api"


class TestIdempotencyConflict:
    def test_default_message(self):
        exc = IdempotencyConflict("key-123")
        assert "key-123" in str(exc)
        assert exc.key == "key-123"


class TestPaymentError:
    def test_with_provider_and_code(self):
        exc = PaymentError("charge failed", provider="stripe", code="card_declined")
        assert exc.provider == "stripe"
        assert exc.code == "card_declined"
        assert "charge failed" in str(exc)

    def test_without_optional_fields(self):
        exc = PaymentError("generic error")
        assert exc.provider is None
        assert exc.code is None
