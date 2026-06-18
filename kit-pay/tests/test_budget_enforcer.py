"""Tests for kit_pay.budget_enforcer using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from kit_pay.budget_enforcer import BudgetEnforcer, BudgetStatus, ChargeRecord, PaymentError


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def enforcer(redis):
    return BudgetEnforcer(redis)


class TestBudgetEnforcer:
    def test_no_limit_returns_unenforced(self, enforcer):
        status = enforcer.check_limit("cust_new")
        assert status.enforced is False
        assert status.used == 0.0

    def test_set_and_check_limit(self, enforcer):
        enforcer.set_limit("cust_001", 100.0, period="monthly")
        status = enforcer.check_limit("cust_001")
        assert status.enforced is True
        assert status.limit == 100.0
        assert status.remaining == 100.0
        assert status.used == 0.0

    def test_record_charge_tracks_usage(self, enforcer):
        enforcer.set_limit("cust_002", 50.0)
        record = enforcer.record_charge("cust_002", 20.0, description="API call", provider="stripe")
        assert isinstance(record, ChargeRecord)
        assert record.amount == 20.0

        status = enforcer.check_limit("cust_002")
        assert status.used == 20.0
        assert status.remaining == 30.0

    def test_record_charge_blocks_when_over_budget(self, enforcer):
        enforcer.set_limit("cust_003", 10.0)
        enforcer.record_charge("cust_003", 8.0)

        with pytest.raises(PaymentError, match="exceed budget"):
            enforcer.record_charge("cust_003", 5.0)  # 8 + 5 > 10

    def test_record_charge_allows_exact_remaining(self, enforcer):
        enforcer.set_limit("cust_004", 10.0)
        enforcer.record_charge("cust_004", 7.0)
        # Exactly 3.0 remaining, should be allowed
        record = enforcer.record_charge("cust_004", 3.0)
        assert record.amount == 3.0

    def test_get_history(self, enforcer):
        enforcer.set_limit("cust_005", 100.0)
        enforcer.record_charge("cust_005", 10.0, description="charge 1")
        enforcer.record_charge("cust_005", 20.0, description="charge 2")

        history = enforcer.get_history("cust_005")
        assert len(history) == 2
        amounts = [h.amount for h in history]
        assert 10.0 in amounts
        assert 20.0 in amounts


class TestBudgetStatus:
    def test_dataclass_fields(self):
        status = BudgetStatus(
            customer_id="c1",
            used=50.0,
            limit=100.0,
            remaining=50.0,
            period="monthly",
            enforced=True,
        )
        assert status.customer_id == "c1"
        assert status.remaining == 50.0
