"""API call cost tracking and budget enforcement."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from kit_core.redis import RedisClient


class Period(Enum):
    """Supported budget/reporting periods."""

    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


_PERIOD_SECONDS: dict[Period, int] = {
    Period.HOURLY: 3600,
    Period.DAILY: 86400,
    Period.MONTHLY: 2592000,  # 30 days
}


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    """Snapshot of budget consumption for a provider."""

    used: float
    limit: float
    remaining: float
    percentage: float


class CostTracker:
    """Track per-provider, per-endpoint API call costs in Redis.

    Costs are recorded in sorted sets keyed by period bucket so they
    naturally expire and roll over.
    """

    def __init__(self, redis: RedisClient, *, key_prefix: str = "kit:cost") -> None:
        self._redis = redis
        self.key_prefix = key_prefix

    # -- Key helpers ---------------------------------------------------------

    def _bucket(self, period: Period) -> str:
        """Return a time-bucket identifier for *period*."""
        now = int(time.time())
        window = _PERIOD_SECONDS[period]
        return str(now // window)

    def _usage_key(self, provider: str, period: Period) -> str:
        bucket = self._bucket(period)
        return f"{self.key_prefix}:{provider}:{period.value}:{bucket}"

    def _endpoint_key(self, provider: str, endpoint: str, period: Period) -> str:
        bucket = self._bucket(period)
        return f"{self.key_prefix}:{provider}:{endpoint}:{period.value}:{bucket}"

    def _budget_key(self, provider: str, period: Period) -> str:
        return f"{self.key_prefix}:budget:{provider}:{period.value}"

    # -- Public API ----------------------------------------------------------

    def record(
        self,
        provider: str,
        endpoint: str,
        cost: float,
        tokens: int | None = None,
    ) -> None:
        """Record a single API call cost.

        Parameters
        ----------
        provider:
            Provider name (e.g. ``"openai"``).
        endpoint:
            Endpoint or operation identifier.
        cost:
            Monetary cost of the call.
        tokens:
            Optional token count associated with the call.
        """
        pipe = self._redis.client.pipeline()
        for period in Period:
            ttl = _PERIOD_SECONDS[period] * 2  # keep data for two full periods

            usage_key = self._usage_key(provider, period)
            pipe.incrbyfloat(usage_key, cost)
            pipe.expire(usage_key, ttl)

            ep_key = self._endpoint_key(provider, endpoint, period)
            pipe.incrbyfloat(ep_key, cost)
            pipe.expire(ep_key, ttl)

            if tokens is not None:
                token_key = f"{ep_key}:tokens"
                pipe.incrby(token_key, tokens)
                pipe.expire(token_key, ttl)

        pipe.execute()

    def get_usage(self, provider: str, period: Period) -> float:
        """Return the total cost for *provider* in the current *period*."""
        raw = self._redis.client.get(self._usage_key(provider, period))
        if raw is None:
            return 0.0
        return float(raw)

    def get_endpoint_usage(self, provider: str, endpoint: str, period: Period) -> float:
        """Return the cost for a specific *endpoint* in the current *period*."""
        raw = self._redis.client.get(self._endpoint_key(provider, endpoint, period))
        if raw is None:
            return 0.0
        return float(raw)

    def set_budget(self, provider: str, limit: float, period: Period) -> None:
        """Set a spending budget for *provider*."""
        self._redis.client.set(self._budget_key(provider, period), str(limit))

    def check_budget(self, provider: str, period: Period | None = None) -> BudgetStatus:
        """Return the current budget status for *provider*.

        When *period* is ``None`` it defaults to ``DAILY``.
        """
        period = period or Period.DAILY
        raw_limit: Any = self._redis.client.get(self._budget_key(provider, period))
        limit = float(raw_limit) if raw_limit else 0.0
        used = self.get_usage(provider, period)
        remaining = max(0.0, limit - used)
        percentage = (used / limit * 100.0) if limit > 0 else 0.0
        return BudgetStatus(
            used=round(used, 6),
            limit=round(limit, 6),
            remaining=round(remaining, 6),
            percentage=round(percentage, 2),
        )
