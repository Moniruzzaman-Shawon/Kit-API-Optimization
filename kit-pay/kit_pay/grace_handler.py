from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from redis import Redis

from kit_pay.plan_state import PlanState, PlanStateManager


@dataclass
class GracePeriod:
    subscription_id: str
    started_at: float
    ends_at: float
    reason: str
    reminders_sent: list[float] = field(default_factory=list)


class GraceHandler:
    """Manages payment grace periods and integrates with :class:`PlanStateManager`."""

    def __init__(
        self,
        redis: Redis,
        plan_state: PlanStateManager,
        grace_days: int = 7,
        reminder_intervals: list[int] | None = None,
        prefix: str = "kit:grace",
    ) -> None:
        self._redis = redis
        self._plan_state = plan_state
        self.grace_days = grace_days
        self.reminder_intervals = reminder_intervals or [3, 1]
        self._prefix = prefix

    def start_grace(
        self, subscription_id: str, reason: str = "payment_failed"
    ) -> GracePeriod:
        """Begin a grace period for the given subscription.

        Transitions the subscription to the GRACE state and stores the
        grace period record in Redis.
        """
        now = time.time()
        ends_at = now + self.grace_days * 86400

        self._plan_state.transition(subscription_id, PlanState.GRACE)

        # Update grace_until on the subscription
        sub = self._plan_state.get(subscription_id)
        sub.grace_until = ends_at
        self._plan_state._save(sub)

        grace = GracePeriod(
            subscription_id=subscription_id,
            started_at=now,
            ends_at=ends_at,
            reason=reason,
        )
        self._save(grace)
        return grace

    def check_grace(self, subscription_id: str) -> GracePeriod | None:
        """Return the current grace period for a subscription, or None."""
        key = f"{self._prefix}:{subscription_id}"
        raw = self._redis.get(key)
        if raw is None:
            return None
        return self._deserialise(json.loads(raw))

    def extend_grace(self, subscription_id: str, days: int) -> GracePeriod:
        """Extend the grace period by the given number of days.

        Raises ``KeyError`` if no active grace period exists.
        """
        grace = self.check_grace(subscription_id)
        if grace is None:
            raise KeyError(
                f"No active grace period for subscription {subscription_id!r}"
            )
        grace.ends_at += days * 86400

        # Keep the subscription's grace_until in sync
        sub = self._plan_state.get(subscription_id)
        sub.grace_until = grace.ends_at
        self._plan_state._save(sub)

        self._save(grace)
        return grace

    def end_grace(
        self, subscription_id: str, reason: str = "resolved"
    ) -> None:
        """End the grace period.

        If *reason* is ``"resolved"`` the subscription transitions back to
        ACTIVE.  Otherwise it is transitioned to CANCELLED.
        """
        key = f"{self._prefix}:{subscription_id}"

        if reason == "resolved":
            self._plan_state.transition(subscription_id, PlanState.ACTIVE)
        else:
            self._plan_state.transition(subscription_id, PlanState.CANCELLED)

        sub = self._plan_state.get(subscription_id)
        sub.grace_until = None
        self._plan_state._save(sub)

        self._redis.delete(key)

    def due_reminders(self, subscription_id: str) -> list[int]:
        """Return reminder intervals that are due but not yet sent."""
        grace = self.check_grace(subscription_id)
        if grace is None:
            return []

        now = time.time()
        days_remaining = (grace.ends_at - now) / 86400
        due: list[int] = []
        for interval in self.reminder_intervals:
            if days_remaining <= interval and interval not in grace.reminders_sent:
                due.append(interval)
        return due

    def mark_reminder_sent(
        self, subscription_id: str, interval: int
    ) -> None:
        """Record that a reminder for the given interval has been sent."""
        grace = self.check_grace(subscription_id)
        if grace is None:
            return
        if interval not in grace.reminders_sent:
            grace.reminders_sent.append(interval)
            self._save(grace)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save(self, grace: GracePeriod) -> None:
        key = f"{self._prefix}:{grace.subscription_id}"
        self._redis.set(key, json.dumps(asdict(grace)))

    @staticmethod
    def _deserialise(data: dict[str, Any]) -> GracePeriod:
        return GracePeriod(**data)
