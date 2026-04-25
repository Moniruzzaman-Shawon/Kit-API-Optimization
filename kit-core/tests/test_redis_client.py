"""Tests for kit_core.redis_client using fakeredis."""

from __future__ import annotations

import pytest
import fakeredis.aioredis

from kit_core.redis_client import RedisClient


@pytest.fixture
def redis_client():
    """Create a RedisClient backed by fakeredis."""
    client = RedisClient.__new__(RedisClient)
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client._url = "redis://fake"
    client._pool = None
    client._client = fake
    return client


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    RedisClient.reset_instances()
    yield
    RedisClient.reset_instances()


class TestRedisClientSingleton:
    def test_same_url_returns_same_instance(self):
        a = RedisClient.get_instance("redis://localhost:6379/0")
        b = RedisClient.get_instance("redis://localhost:6379/0")
        assert a is b

    def test_different_url_returns_different_instance(self):
        a = RedisClient.get_instance("redis://localhost:6379/0")
        b = RedisClient.get_instance("redis://localhost:6379/1")
        assert a is not b

    def test_reset_clears_instances(self):
        a = RedisClient.get_instance("redis://localhost:6379/0")
        RedisClient.reset_instances()
        b = RedisClient.get_instance("redis://localhost:6379/0")
        assert a is not b


@pytest.mark.asyncio
class TestRedisClientOperations:
    async def test_set_and_get(self, redis_client):
        await redis_client.set("key1", "value1")
        result = await redis_client.get("key1")
        assert result == "value1"

    async def test_get_nonexistent(self, redis_client):
        result = await redis_client.get("nonexistent")
        assert result is None

    async def test_set_with_ttl(self, redis_client):
        await redis_client.set("key2", "val", ttl=100)
        result = await redis_client.get("key2")
        assert result == "val"

    async def test_delete(self, redis_client):
        await redis_client.set("key3", "val")
        deleted = await redis_client.delete("key3")
        assert deleted == 1
        assert await redis_client.get("key3") is None

    async def test_incr(self, redis_client):
        await redis_client.set("counter", 0)
        result = await redis_client.incr("counter")
        assert result == 1
        result = await redis_client.incr("counter", 5)
        assert result == 6

    async def test_exists(self, redis_client):
        await redis_client.set("exists_key", "yes")
        assert await redis_client.exists("exists_key") == 1
        assert await redis_client.exists("nope") == 0
