"""Tests for kit_data.counter using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from kit_core.redis_client import RedisClient
from kit_data.counter import Counter


@pytest.fixture
def redis_client():
    client = RedisClient.__new__(RedisClient)
    client._url = "redis://fake"
    client._pool = None
    client._client = fakeredis.FakeRedis(decode_responses=True)
    return client


@pytest.fixture
def counter(redis_client):
    return Counter(redis_client, namespace="c")


def test_incr_returns_new_value(counter):
    assert counter.incr("likes") == 1
    assert counter.incr("likes", 4) == 5
    assert counter.get("likes") == 5


def test_decr(counter):
    counter.incr("stock", 10)
    assert counter.decr("stock", 3) == 7


def test_get_unset_is_zero(counter):
    assert counter.get("never") == 0


def test_get_many(counter):
    counter.incr("a", 2)
    counter.incr("b", 5)
    assert counter.get_many(["a", "b", "missing"]) == {"a": 2, "b": 5, "missing": 0}


def test_get_many_empty(counter):
    assert counter.get_many([]) == {}


def test_set_and_reset(counter):
    counter.set("views", 99)
    assert counter.get("views") == 99
    counter.reset("views")
    assert counter.get("views") == 0
