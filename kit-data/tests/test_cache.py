"""Tests for kit_data.cache using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from kit_core.redis_client import RedisClient
from kit_data.cache import Cache, cached


@pytest.fixture
def redis_client():
    client = RedisClient.__new__(RedisClient)
    client._url = "redis://fake"
    client._pool = None
    client._client = fakeredis.FakeRedis(decode_responses=True)
    return client


@pytest.fixture
def cache(redis_client):
    return Cache(redis_client, namespace="t", default_ttl=60, jitter=0)


def test_set_get_roundtrip(cache):
    cache.set("k", {"a": 1})
    assert cache.get("k") == {"a": 1}


def test_get_miss_returns_none(cache):
    assert cache.get("missing") is None


def test_get_or_set_computes_once_then_caches(cache):
    calls = []

    def loader():
        calls.append(1)
        return {"v": 42}

    assert cache.get_or_set("k", loader) == {"v": 42}
    assert cache.get_or_set("k", loader) == {"v": 42}
    assert calls == [1]  # loader ran only on the miss


def test_delete_invalidates(cache):
    cache.set("k", "v")
    cache.delete("k")
    assert cache.get("k") is None


def test_set_applies_ttl(cache, redis_client):
    cache.set("k", "v", ttl=120)
    assert 0 < redis_client.client.ttl("t:k") <= 120


def test_cached_decorator(redis_client):
    calls = []

    @cached(ttl=60, redis=redis_client, namespace="dec")
    def compute(x):
        calls.append(x)
        return x * 2

    assert compute(5) == 10
    assert compute(5) == 10  # served from cache
    assert calls == [5]


def test_cached_decorator_custom_key(redis_client):
    @cached(redis=redis_client, key=lambda user_id, **_: f"u:{user_id}")
    def fetch(user_id, verbose=False):
        return {"id": user_id}

    assert fetch(7) == {"id": 7}
    assert fetch(7, verbose=True) == {"id": 7}  # same key -> cached
