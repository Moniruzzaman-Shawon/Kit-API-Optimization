from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis


class RedisClient:
    """Async Redis client with connection pooling and singleton access."""

    _instances: dict[str, RedisClient] = {}
    _lock = threading.Lock()

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._url = url
        self._pool = aioredis.ConnectionPool.from_url(
            url,
            max_connections=20,
            decode_responses=True,
        )
        self._client = aioredis.Redis(connection_pool=self._pool)

    @classmethod
    def get_instance(cls, url: str = "redis://localhost:6379/0") -> RedisClient:
        """Get or create a singleton RedisClient for the given URL."""
        with cls._lock:
            if url not in cls._instances:
                cls._instances[url] = cls(url)
            return cls._instances[url]

    @classmethod
    def reset_instances(cls) -> None:
        """Clear all singleton instances (useful for testing)."""
        with cls._lock:
            cls._instances.clear()

    async def health_check(self) -> bool:
        """Check if Redis is reachable."""
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(
        self,
        key: str,
        value: str | bytes | int | float,
        ttl: int | None = None,
    ) -> None:
        if ttl:
            await self._client.setex(key, ttl, value)
        else:
            await self._client.set(key, value)

    async def delete(self, *keys: str) -> int:
        return await self._client.delete(*keys)

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self._client.incrby(key, amount)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self._client.expire(key, seconds)

    async def exists(self, *keys: str) -> int:
        return await self._client.exists(*keys)

    async def ttl(self, key: str) -> int:
        return await self._client.ttl(key)

    @asynccontextmanager
    async def pipeline(self, transaction: bool = True) -> AsyncIterator[Any]:
        """Context manager for Redis pipeline (batch operations)."""
        pipe = self._client.pipeline(transaction=transaction)
        try:
            yield pipe
            await pipe.execute()
        finally:
            await pipe.reset()

    async def close(self) -> None:
        await self._client.aclose()
        await self._pool.aclose()

    @property
    def client(self) -> aioredis.Redis:
        """Access the underlying redis client directly."""
        return self._client
