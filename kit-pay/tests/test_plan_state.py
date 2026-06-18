"""Tests for kit_pay.plan_state using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from kit_pay.plan_state import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    PlanState,
    PlanStateManager,
    Subscription,
)


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def manager(redis):
    return PlanStateManager(redis)


@pytest.fixture
def trial_sub():
    return Subscription(
        id="sub_001",
        customer_id="cust_123",
        plan_id="plan_pro",
        state=PlanState.TRIAL,
        current_period_end=9999999999.0,
    )


class TestPlanStateManager:
    def test_create_and_get(self, manager, trial_sub):
        manager.create(trial_sub)
        result = manager.get("sub_001")
        assert result.id == "sub_001"
        assert result.state == PlanState.TRIAL
        assert result.customer_id == "cust_123"

    def test_get_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.get("nonexistent")

    def test_valid_transition_trial_to_active(self, manager, trial_sub):
        manager.create(trial_sub)
        result = manager.transition("sub_001", PlanState.ACTIVE)
        assert result.state == PlanState.ACTIVE

    def test_valid_transition_active_to_past_due(self, manager, trial_sub):
        manager.create(trial_sub)
        manager.transition("sub_001", PlanState.ACTIVE)
        result = manager.transition("sub_001", PlanState.PAST_DUE)
        assert result.state == PlanState.PAST_DUE

    def test_invalid_transition_raises(self, manager, trial_sub):
        manager.create(trial_sub)
        with pytest.raises(InvalidTransitionError, match="Cannot transition"):
            manager.transition("sub_001", PlanState.PAST_DUE)  # TRIAL -> PAST_DUE not allowed

    def test_is_active_for_active_states(self, manager, trial_sub):
        manager.create(trial_sub)
        assert manager.is_active("sub_001") is True  # TRIAL is active

        manager.transition("sub_001", PlanState.ACTIVE)
        assert manager.is_active("sub_001") is True

    def test_is_active_false_for_expired(self, manager, trial_sub):
        manager.create(trial_sub)
        manager.transition("sub_001", PlanState.EXPIRED)
        assert manager.is_active("sub_001") is False

    def test_is_active_false_for_nonexistent(self, manager):
        assert manager.is_active("nope") is False

    def test_reactivation_from_cancelled(self, manager, trial_sub):
        manager.create(trial_sub)
        manager.transition("sub_001", PlanState.CANCELLED)
        assert manager.is_active("sub_001") is False
        # Reactivate
        manager.transition("sub_001", PlanState.ACTIVE)
        assert manager.is_active("sub_001") is True


class TestValidTransitions:
    def test_all_states_have_transitions(self):
        for state in PlanState:
            assert state in VALID_TRANSITIONS

    def test_trial_can_go_to_active_cancelled_expired(self):
        allowed = VALID_TRANSITIONS[PlanState.TRIAL]
        assert PlanState.ACTIVE in allowed
        assert PlanState.CANCELLED in allowed
        assert PlanState.EXPIRED in allowed
