"""Redis-backed cache-aside with single-flight stampede protection."""

from __future__ import annotations

import functools
import hashlib
import json
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from kit_core.redis import RedisClient

F = TypeVar("F", bound=Callable[..., Any])

_DEFAULT_TTL = 300


class Cache:
    """Cache-aside store over Redis with stampede (thundering-herd) protection.

    ``get_or_set`` is the core: on a cache miss it uses a short Redis lock so that
    when many workers request the same missing key at once, only one recomputes the
    value (single-flight) and the rest read the freshly cached result. A small TTL
    jitter spreads expirations so hot keys don't all expire on the same tick.

    Values are JSON-serialized, so they must be JSON-compatible.
    """

    def __init__(
        self,
        redis: RedisClient,
        *,
        namespace: str = "kit:cache",
        default_ttl: int = _DEFAULT_TTL,
        lock_ttl: int = 10,
        jitter: float = 0.1,
    ) -> None:
        self._redis = redis
        self._namespace = namespace
        self._default_ttl = default_ttl
        self._lock_ttl = lock_ttl
        self._jitter = jitter

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._namespace}:lock:{key}"

    def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or ``None`` on a miss."""
        raw = self._redis.client.get(self._key(key))
        return None if raw is None else json.loads(raw)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Cache *value* under *key* with a (jittered) TTL in seconds."""
        ttl = self._default_ttl if ttl is None else ttl
        self._redis.client.set(self._key(key), json.dumps(value), ex=self._jittered(ttl))

    def delete(self, *keys: str) -> None:
        """Invalidate one or more cached keys."""
        if keys:
            self._redis.client.delete(*[self._key(k) for k in keys])

    def get_or_set(self, key: str, loader: Callable[[], Any], ttl: int | None = None) -> Any:
        """Return the cached value, or compute it via *loader* and cache it.

        Stampede-safe: only one caller computes a missing key at a time.
        """
        hit = self.get(key)
        if hit is not None:
            return hit

        lock = self._lock_key(key)
        if self._redis.client.set(lock, "1", nx=True, ex=self._lock_ttl):
            try:
                hit = self.get(key)  # double-check after winning the lock
                if hit is not None:
                    return hit
                value = loader()
                self.set(key, value, ttl)
                return value
            finally:
                self._redis.client.delete(lock)

        # Another caller is computing — wait for the value to appear.
        deadline = time.monotonic() + self._lock_ttl
        while time.monotonic() < deadline:
            time.sleep(0.05)
            hit = self.get(key)
            if hit is not None:
                return hit

        # Fail open: compute it ourselves rather than block forever.
        value = loader()
        self.set(key, value, ttl)
        return value

    def _jittered(self, ttl: int) -> int:
        if self._jitter <= 0:
            return ttl
        return max(1, int(ttl * (1 + random.uniform(0, self._jitter))))


def _default_key(fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    raw = f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
    return hashlib.sha1(raw.encode()).hexdigest()


def cached(
    ttl: int | None = None,
    *,
    key: Callable[..., str] | None = None,
    namespace: str = "kit:cache",
    redis: RedisClient | None = None,
) -> Callable[[F], F]:
    """Decorator that memoizes a function's result in Redis (stampede-safe).

    Parameters
    ----------
    ttl:
        Cache TTL in seconds (defaults to the cache's default).
    key:
        Optional callable receiving the wrapped function's arguments and returning
        the cache key. Defaults to a hash of the qualified name and arguments.
    redis:
        Optional ``RedisClient`` instance.
    """

    def decorator(fn: F) -> F:
        cache = Cache(redis or RedisClient(), namespace=namespace)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ck = key(*args, **kwargs) if key else _default_key(fn, args, kwargs)
            return cache.get_or_set(ck, lambda: fn(*args, **kwargs), ttl)

        return wrapper  # type: ignore[return-value]

    return decorator
