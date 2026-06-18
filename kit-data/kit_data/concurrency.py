"""Redis-backed concurrency limiter (bulkhead) for bursts of expensive work."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from kit_core.redis import RedisClient

from kit_data.exceptions import ConcurrencyLimitExceeded


class ConcurrencyLimiter:
    """Cap the number of concurrent in-flight operations across all workers.

    Implements the bulkhead pattern with a Redis sorted set of in-flight tokens
    scored by acquisition time. Stale tokens older than ``max_hold_seconds`` are
    trimmed automatically, so a crashed holder cannot leak a slot forever. Use it to
    protect a scarce resource (a database, a slow upstream) from a burst of requests.

    Example
    -------
    >>> limiter = ConcurrencyLimiter(redis, name="report-gen", max_concurrent=10)
    >>> with limiter.slot():
    ...     build_expensive_report()
    """

    def __init__(
        self,
        redis: RedisClient,
        *,
        name: str,
        max_concurrent: int,
        max_hold_seconds: int = 30,
        key_prefix: str = "kit:bulkhead",
    ) -> None:
        self._redis = redis
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_hold_seconds = max_hold_seconds
        self.key_prefix = key_prefix

    def _key(self) -> str:
        return f"{self.key_prefix}:{self.name}"

    def acquire(self) -> str:
        """Claim a slot; return a token, or raise ``ConcurrencyLimitExceeded``."""
        key = self._key()
        now = time.time()
        token = uuid.uuid4().hex
        client = self._redis.client
        # Add-then-check: claim a slot, trim stale holders, then verify capacity.
        client.zadd(key, {token: now})
        client.zremrangebyscore(key, 0, now - self.max_hold_seconds)
        client.expire(key, self.max_hold_seconds)
        if client.zcard(key) > self.max_concurrent:
            client.zrem(key, token)
            raise ConcurrencyLimitExceeded(self.name, self.max_concurrent)
        return token

    def release(self, token: str) -> None:
        """Release a previously acquired slot."""
        self._redis.client.zrem(self._key(), token)

    def in_flight(self) -> int:
        """Return the current number of in-flight operations (after trimming)."""
        key = self._key()
        self._redis.client.zremrangebyscore(key, 0, time.time() - self.max_hold_seconds)
        return self._redis.client.zcard(key)

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Context manager that acquires a slot on enter and releases on exit."""
        token = self.acquire()
        try:
            yield
        finally:
            self.release(token)
