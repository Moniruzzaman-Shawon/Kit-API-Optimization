"""Tests for kit_api.circuit_breaker using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from kit_api.circuit_breaker import CircuitBreaker, State
from kit_core.exceptions import CircuitOpen
from kit_core.redis_client import RedisClient


@pytest.fixture
def redis_client():
    """Create a RedisClient backed by sync fakeredis."""
    client = RedisClient.__new__(RedisClient)
    fake = fakeredis.FakeRedis(decode_responses=True)
    client._url = "redis://fake"
    client._pool = None
    client._client = fake
    return client


@pytest.fixture
def cb(redis_client):
    return CircuitBreaker(
        redis_client,
        name="test-service",
        failure_threshold=3,
        recovery_timeout=10,
        half_open_max_calls=1,
    )


class TestCircuitBreaker:
    def test_starts_closed(self, cb):
        assert cb.state == State.CLOSED

    def test_allows_requests_when_closed(self, cb):
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self, cb):
        for _ in range(3):
            cb.record_failure()
        assert cb.state == State.OPEN

    def test_raises_when_open(self, cb):
        for _ in range(3):
            cb.record_failure()
        with pytest.raises(CircuitOpen):
            cb.allow_request()

    def test_success_resets_failure_count(self, cb):
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Should still be closed since we didn't hit threshold
        assert cb.state == State.CLOSED
        # Two more failures should not trip it (counter was reset)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == State.CLOSED

    def test_reset_clears_state(self, cb):
        for _ in range(3):
            cb.record_failure()
        assert cb.state == State.OPEN
        cb.reset()
        assert cb.state == State.CLOSED
