from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PaymentAdapter(Protocol):
    """Protocol that all payment provider adapters must satisfy."""

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify the authenticity of an incoming webhook payload."""
        ...

    def create_charge(
        self,
        amount: int,
        currency: str,
        customer_id: str,
        *,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a one-off charge."""
        ...

    def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        *,
        trial_days: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a recurring subscription."""
        ...

    def cancel_subscription(
        self, subscription_id: str, *, at_period_end: bool = True
    ) -> dict[str, Any]:
        """Cancel a subscription."""
        ...

    def refund(
        self,
        charge_id: str,
        *,
        amount: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Issue a full or partial refund."""
        ...


from kit_pay.adapters.stripe_adapter import StripeAdapter
from kit_pay.adapters.paddle_adapter import PaddleAdapter

__all__ = [
    "PaymentAdapter",
    "StripeAdapter",
    "PaddleAdapter",
]
