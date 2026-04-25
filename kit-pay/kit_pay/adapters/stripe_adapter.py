from __future__ import annotations

from typing import Any


class StripeAdapter:
    """Adapter for Stripe payment operations.

    Requires the ``stripe`` package (``pip install kit-pay[stripe]``).
    """

    def __init__(self, api_key: str) -> None:
        try:
            import stripe as _stripe
        except ImportError as exc:
            raise ImportError(
                "The stripe package is required. Install with: pip install kit-pay[stripe]"
            ) from exc

        _stripe.api_key = api_key
        self._stripe = _stripe

    # ------------------------------------------------------------------
    # Webhook verification
    # ------------------------------------------------------------------

    def verify_webhook(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """Verify a Stripe webhook signature."""
        try:
            self._stripe.Webhook.construct_event(payload, signature, secret)
            return True
        except (
            self._stripe.error.SignatureVerificationError,
            ValueError,
        ):
            return False

    # ------------------------------------------------------------------
    # Charges
    # ------------------------------------------------------------------

    def create_charge(
        self,
        amount: int,
        currency: str,
        customer_id: str,
        *,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe PaymentIntent."""
        params: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "customer": customer_id,
            "confirm": True,
        }
        if metadata:
            params["metadata"] = metadata

        kwargs: dict[str, Any] = {}
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key

        intent = self._stripe.PaymentIntent.create(**params, **kwargs)
        return dict(intent)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        *,
        trial_days: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe subscription."""
        params: dict[str, Any] = {
            "customer": customer_id,
            "items": [{"price": plan_id}],
        }
        if trial_days is not None:
            params["trial_period_days"] = trial_days
        if metadata:
            params["metadata"] = metadata

        sub = self._stripe.Subscription.create(**params)
        return dict(sub)

    def cancel_subscription(
        self, subscription_id: str, *, at_period_end: bool = True
    ) -> dict[str, Any]:
        """Cancel a Stripe subscription."""
        if at_period_end:
            sub = self._stripe.Subscription.modify(
                subscription_id, cancel_at_period_end=True
            )
        else:
            sub = self._stripe.Subscription.delete(subscription_id)
        return dict(sub)

    # ------------------------------------------------------------------
    # Refunds
    # ------------------------------------------------------------------

    def refund(
        self,
        charge_id: str,
        *,
        amount: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Issue a Stripe refund."""
        params: dict[str, Any] = {"payment_intent": charge_id}
        if amount is not None:
            params["amount"] = amount
        if reason:
            params["reason"] = reason

        refund = self._stripe.Refund.create(**params)
        return dict(refund)
