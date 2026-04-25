from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx


class PaddleAdapter:
    """Adapter for Paddle payment operations.

    Uses ``httpx`` to communicate with the Paddle API.
    """

    BASE_URL = "https://api.paddle.com"
    SANDBOX_URL = "https://sandbox-api.paddle.com"

    def __init__(
        self,
        api_key: str,
        *,
        sandbox: bool = False,
    ) -> None:
        self._api_key = api_key
        self._base_url = self.SANDBOX_URL if sandbox else self.BASE_URL
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Webhook verification
    # ------------------------------------------------------------------

    def verify_webhook(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """Verify a Paddle webhook signature using HMAC-SHA256."""
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Transactions (charges)
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
        """Create a Paddle transaction (one-off charge)."""
        body: dict[str, Any] = {
            "items": [
                {
                    "price": {
                        "unit_price": {
                            "amount": str(amount),
                            "currency_code": currency,
                        },
                        "product_id": (
                            metadata.get("product_id", "") if metadata else ""
                        ),
                    },
                    "quantity": 1,
                }
            ],
            "customer_id": customer_id,
        }
        if metadata:
            body["custom_data"] = metadata

        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp = self._client.post("/transactions", json=body, headers=headers)
        resp.raise_for_status()
        return resp.json().get("data", resp.json())

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
        """Create a Paddle subscription."""
        body: dict[str, Any] = {
            "customer_id": customer_id,
            "items": [{"price_id": plan_id, "quantity": 1}],
        }
        if trial_days is not None:
            body["trial_period_days"] = trial_days
        if metadata:
            body["custom_data"] = metadata

        resp = self._client.post("/subscriptions", json=body)
        resp.raise_for_status()
        return resp.json().get("data", resp.json())

    def cancel_subscription(
        self, subscription_id: str, *, at_period_end: bool = True
    ) -> dict[str, Any]:
        """Cancel a Paddle subscription."""
        body: dict[str, Any] = {
            "effective_from": (
                "next_billing_period" if at_period_end else "immediately"
            ),
        }
        resp = self._client.post(
            f"/subscriptions/{subscription_id}/cancel", json=body
        )
        resp.raise_for_status()
        return resp.json().get("data", resp.json())

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
        """Create a Paddle refund (credit) for a transaction."""
        body: dict[str, Any] = {"transaction_id": charge_id}
        if amount is not None:
            body["amount"] = str(amount)
        if reason:
            body["reason"] = reason

        resp = self._client.post("/adjustments", json=body)
        resp.raise_for_status()
        return resp.json().get("data", resp.json())
