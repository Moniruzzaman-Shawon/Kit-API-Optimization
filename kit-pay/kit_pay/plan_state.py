from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from redis import Redis


class PlanState(Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    GRACE = "grace"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# Valid state transitions: source -> {allowed targets}
VALID_TRANSITIONS: dict[PlanState, set[PlanState]] = {
    PlanState.TRIAL: {PlanState.ACTIVE, PlanState.CANCELLED, PlanState.EXPIRED},
    PlanState.ACTIVE: {PlanState.PAST_DUE, PlanState.CANCELLED, PlanState.EXPIRED},
    PlanState.PAST_DUE: {PlanState.ACTIVE, PlanState.GRACE, PlanState.CANCELLED},
    PlanState.GRACE: {PlanState.ACTIVE, PlanState.CANCELLED, PlanState.EXPIRED},
    PlanState.CANCELLED: {PlanState.ACTIVE},  # reactivation
    PlanState.EXPIRED: {PlanState.ACTIVE},  # reactivation
}


@dataclass
class Subscription:
    id: str
    customer_id: str
    plan_id: str
    state: PlanState
    current_period_end: float
    grace_until: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""


class PlanStateManager:
    """Manages subscription plan state as a finite state machine."""

    def __init__(self, redis: Redis, prefix: str = "kit:plan") -> None:
        self._redis = redis
        self._prefix = prefix

    def create(self, subscription: Subscription) -> Subscription:
        """Persist a new subscription."""
        self._save(subscription)
        return subscription

    def get(self, subscription_id: str) -> Subscription:
        """Retrieve a subscription by ID.

        Raises ``KeyError`` if the subscription does not exist.
        """
        key = f"{self._prefix}:{subscription_id}"
        raw = self._redis.get(key)
        if raw is None:
            raise KeyError(f"Subscription {subscription_id!r} not found")
        return self._deserialise(json.loads(raw))

    def transition(
        self, subscription_id: str, new_state: PlanState
    ) -> Subscription:
        """Transition a subscription to a new state.

        Validates that the transition is allowed according to the state machine.
        Raises ``InvalidTransitionError`` if the transition is not permitted.
        """
        sub = self.get(subscription_id)
        allowed = VALID_TRANSITIONS.get(sub.state, set())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {sub.state.value} to {new_state.value}"
            )
        sub.state = new_state
        sub.metadata["last_transition"] = time.time()
        self._save(sub)
        return sub

    def is_active(self, subscription_id: str) -> bool:
        """Return True if the subscription is in an active-access state.

        Active-access states include TRIAL, ACTIVE, PAST_DUE, and GRACE.
        """
        try:
            sub = self.get(subscription_id)
        except KeyError:
            return False
        return sub.state in {
            PlanState.TRIAL,
            PlanState.ACTIVE,
            PlanState.PAST_DUE,
            PlanState.GRACE,
        }

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save(self, sub: Subscription) -> None:
        key = f"{self._prefix}:{sub.id}"
        data = asdict(sub)
        data["state"] = sub.state.value
        self._redis.set(key, json.dumps(data))

    @staticmethod
    def _deserialise(data: dict[str, Any]) -> Subscription:
        data["state"] = PlanState(data["state"])
        return Subscription(**data)
