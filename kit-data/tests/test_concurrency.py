"""Tests for kit_data.concurrency using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from kit_core.redis_client import RedisClient
from kit_data.concurrency import ConcurrencyLimiter
from kit_data.exceptions import ConcurrencyLimitExceeded


@pytest.fixture
def redis_client():
    client = RedisClient.__new__(RedisClient)
    client._url = "redis://fake"
    client._pool = None
    client._client = fakeredis.FakeRedis(decode_responses=True)
    return client


@pytest.fixture
def limiter(redis_client):
    return ConcurrencyLimiter(redis_client, name="job", max_concurrent=2)


def test_acquire_up_to_limit(limiter):
    limiter.acquire()
    limiter.acquire()
    assert limiter.in_flight() == 2


def test_exceeding_limit_raises(limiter):
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(ConcurrencyLimitExceeded):
        limiter.acquire()


def test_release_frees_a_slot(limiter):
    t1 = limiter.acquire()
    limiter.acquire()
    limiter.release(t1)
    assert limiter.in_flight() == 1
    limiter.acquire()  # slot is available again


def test_slot_context_manager_releases(limiter):
    with limiter.slot():
        assert limiter.in_flight() == 1
    assert limiter.in_flight() == 0


def test_exception_carries_name_and_limit(limiter):
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(ConcurrencyLimitExceeded) as exc:
        limiter.acquire()
    assert exc.value.name == "job"
    assert exc.value.limit == 2


def test_stale_tokens_are_trimmed(redis_client):
    limiter = ConcurrencyLimiter(redis_client, name="short", max_concurrent=1, max_hold_seconds=0)
    limiter.acquire()
    # With a zero hold window, the prior token is immediately stale and trimmed.
    limiter.acquire()
    assert limiter.in_flight() <= 1
