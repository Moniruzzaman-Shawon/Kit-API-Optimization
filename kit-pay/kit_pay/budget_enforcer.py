from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from redis import Redis


class PaymentError(Exception):
    """Raised when a payment operation is rejected."""


@dataclass
class ChargeRecord:
    amount: float
    timestamp: float
    description: str
    provider: str


@dataclass
class BudgetStatus:
    customer_id: str
    used: float
    limit: float
    remaining: float
    period: str
    enforced: bool


class BudgetEnforcer:
    """Enforces spending limits per customer over configurable billing periods."""

    def __init__(self, redis: Redis, prefix: str = "kit:budget") -> None:
        self._redis = redis
        self._prefix = prefix

    def set_limit(
        self,
        customer_id: str,
        amount: float,
        period: str = "monthly",
    ) -> None:
        """Set the spending limit for a customer."""
        key = f"{self._prefix}:limit:{customer_id}"
        self._redis.set(key, json.dumps({"amount": amount, "period": period}))

    def record_charge(
        self,
        customer_id: str,
        amount: float,
        description: str = "",
        provider: str = "",
    ) -> ChargeRecord:
        """Record a charge against the customer's budget.

        Raises ``PaymentError`` if the charge would exceed the configured limit.
        """
        status = self.check_limit(customer_id)
        if status.enforced and amount > status.remaining:
            raise PaymentError(
                f"Charge of {amount} would exceed budget for customer "
                f"{customer_id!r} (remaining: {status.remaining})"
            )

        record = ChargeRecord(
            amount=amount,
            timestamp=time.time(),
            description=description,
            provider=provider,
        )
        period_key = self._period_key(customer_id, status.period)
        self._redis.lpush(period_key, json.dumps(asdict(record)))
        # Expire after a generous window so stale data is cleaned up.
        self._redis.expire(period_key, 90 * 86400)
        return record

    def check_limit(self, customer_id: str) -> BudgetStatus:
        """Return the current budget status for a customer."""
        limit_key = f"{self._prefix}:limit:{customer_id}"
        raw = self._redis.get(limit_key)

        if raw is None:
            return BudgetStatus(
                customer_id=customer_id,
                used=0.0,
                limit=0.0,
                remaining=0.0,
                period="monthly",
                enforced=False,
            )

        config = json.loads(raw)
        limit = float(config["amount"])
        period = config["period"]

        charges = self._get_charges_for_period(customer_id, period)
        used = sum(c.amount for c in charges)
        remaining = max(limit - used, 0.0)

        return BudgetStatus(
            customer_id=customer_id,
            used=used,
            limit=limit,
            remaining=remaining,
            period=period,
            enforced=True,
        )

    def get_history(
        self, customer_id: str, period: str = "monthly"
    ) -> list[ChargeRecord]:
        """Return charge records for the customer in the given period."""
        return self._get_charges_for_period(customer_id, period)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _period_key(self, customer_id: str, period: str) -> str:
        tag = _period_tag(period)
        return f"{self._prefix}:charges:{customer_id}:{tag}"

    def _get_charges_for_period(
        self, customer_id: str, period: str
    ) -> list[ChargeRecord]:
        period_key = self._period_key(customer_id, period)
        raw_list = self._redis.lrange(period_key, 0, -1)
        charges: list[ChargeRecord] = []
        period_start = _period_start(period)
        for raw in raw_list:
            data: dict[str, Any] = json.loads(raw)
            record = ChargeRecord(**data)
            if record.timestamp >= period_start:
                charges.append(record)
        return charges


def _period_tag(period: str) -> str:
    """Return a human-readable tag for the current billing period."""
    t = time.gmtime()
    if period == "daily":
        return f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}"
    if period == "weekly":
        iso = time.strftime("%G-W%V", t)
        return iso
    # Default: monthly
    return f"{t.tm_year}-{t.tm_mon:02d}"


def _period_start(period: str) -> float:
    """Return the UTC epoch for the start of the current billing period."""
    import calendar

    t = time.gmtime()
    if period == "daily":
        return float(
            calendar.timegm((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, 0))
        )
    if period == "weekly":
        day_of_week = t.tm_wday  # Monday = 0
        start_day = time.mktime(
            (t.tm_year, t.tm_mon, t.tm_mday - day_of_week, 0, 0, 0, 0, 0, 0)
        )
        return start_day
    # Default: monthly
    return float(
        calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0))
    )
