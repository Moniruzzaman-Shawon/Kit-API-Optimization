"""Sliding-window rate limiter backed by Redis."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from kit_core.exceptions import RateLimitExceeded
from kit_core.redis import RedisClient

F = TypeVar("F", bound=Callable[..., Any])


class RateLimiter:
    """Sliding-window rate limiter using Redis sorted sets.

    Each call is recorded as a member scored by its timestamp. On every
    ``acquire`` the window is trimmed and the remaining count evaluated
    atomically via a Lua script.
    """

    _LUA_ACQUIRE = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local max_req = tonumber(ARGV[3])

    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local current = redis.call('ZCARD', key)
    if current < max_req then
        redis.call('ZADD', key, now, now .. '-' .. math.random(1, 1000000))
        redis.call('EXPIRE', key, window)
        return max_req - current - 1
    end
    return -1
    """

    def __init__(
        self,
        redis: RedisClient,
        *,
        max_requests: int,
        window_seconds: int,
        key_prefix: str = "kit:rl",
    ) -> None:
        self._redis = redis
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix
        self._script: Any | None = None

    def _get_script(self) -> Any:
        if self._script is None:
            self._script = self._redis.client.register_script(self._LUA_ACQUIRE)
        return self._script

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def acquire(self, key: str) -> bool:
        """Try to acquire a request slot.

        Returns ``True`` if the request is allowed, raises
        ``RateLimitExceeded`` otherwise.
        """
        script = self._get_script()
        now = time.time()
        result: int = script(
            keys=[self._key(key)],
            args=[now, self.window_seconds, self.max_requests],
        )
        if result < 0:
            raise RateLimitExceeded(
                f"Rate limit exceeded for key '{key}': "
                f"{self.max_requests} requests per {self.window_seconds}s"
            )
        return True

    def remaining(self, key: str) -> int:
        """Return the number of remaining requests in the current window."""
        redis_key = self._key(key)
        now = time.time()
        self._redis.client.zremrangebyscore(redis_key, 0, now - self.window_seconds)
        current: int = self._redis.client.zcard(redis_key)
        return max(0, self.max_requests - current)

    def reset(self, key: str) -> None:
        """Remove all tracking data for *key*."""
        self._redis.client.delete(self._key(key))


def rate_limit(
    max_requests: int,
    window: int,
    *,
    key_func: Callable[..., str] | None = None,
    redis: RedisClient | None = None,
) -> Callable[[F], F]:
    """Decorator that enforces a rate limit on calls to the wrapped function.

    Parameters
    ----------
    max_requests:
        Maximum number of invocations within *window* seconds.
    window:
        Sliding window duration in seconds.
    key_func:
        Optional callable that receives the same arguments as the wrapped
        function and returns the rate-limit key.  Defaults to the qualified
        function name.
    redis:
        Optional ``RedisClient`` instance.  When ``None`` a default client is
        created via ``RedisClient()``.
    """

    def decorator(fn: F) -> F:
        _redis = redis or RedisClient()
        limiter = RateLimiter(
            _redis,
            max_requests=max_requests,
            window_seconds=window,
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_func(*args, **kwargs) if key_func else fn.__qualname__
            limiter.acquire(key)
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
