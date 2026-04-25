"""Idempotency enforcement using Redis-backed fingerprint storage."""

from __future__ import annotations

import functools
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, TypeVar

from kit_core.exceptions import IdempotencyConflict
from kit_core.redis import RedisClient

F = TypeVar("F", bound=Callable[..., Any])

_DEFAULT_TTL = 3600  # 1 hour


@dataclass(frozen=True, slots=True)
class CachedResponse:
    """Previously stored response for an idempotent request."""

    status_code: int
    body: Any
    headers: dict[str, str]


class IdempotencyStore:
    """Store and retrieve idempotent request fingerprints via Redis."""

    def __init__(self, redis: RedisClient, *, key_prefix: str = "kit:idem") -> None:
        self._redis = redis
        self.key_prefix = key_prefix

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self.key_prefix}:lock:{key}"

    def check(self, key: str) -> CachedResponse | None:
        """Return the cached response for *key*, or ``None``."""
        raw = self._redis.client.get(self._key(key))
        if raw is None:
            return None
        data = json.loads(raw)
        return CachedResponse(
            status_code=data["status_code"],
            body=data["body"],
            headers=data.get("headers", {}),
        )

    def store(self, key: str, response: CachedResponse, ttl: int = _DEFAULT_TTL) -> None:
        """Store a response under *key* with a TTL in seconds."""
        payload = json.dumps(asdict(response))
        self._redis.client.set(self._key(key), payload, ex=ttl)

    def acquire_lock(self, key: str, ttl: int = 30) -> bool:
        """Acquire a processing lock so concurrent duplicates are rejected.

        Returns ``True`` if the lock was acquired, raises
        ``IdempotencyConflict`` if another request already holds it.
        """
        acquired: bool | None = self._redis.client.set(
            self._lock_key(key), "1", nx=True, ex=ttl
        )
        if not acquired:
            raise IdempotencyConflict(
                f"Request with idempotency key '{key}' is already being processed"
            )
        return True

    def release_lock(self, key: str) -> None:
        """Release the processing lock for *key*."""
        self._redis.client.delete(self._lock_key(key))


def idempotent(
    key_func: Callable[..., str],
    *,
    ttl: int = _DEFAULT_TTL,
    redis: RedisClient | None = None,
) -> Callable[[F], F]:
    """Decorator that enforces idempotency on an endpoint handler.

    Parameters
    ----------
    key_func:
        Callable that receives the same arguments as the wrapped function and
        returns a string used as the idempotency key.
    ttl:
        Time-to-live in seconds for cached responses.
    redis:
        Optional ``RedisClient`` instance.
    """

    def decorator(fn: F) -> F:
        _redis = redis or RedisClient()
        store = IdempotencyStore(_redis)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_func(*args, **kwargs)

            # Return cached response if available.
            cached = store.check(key)
            if cached is not None:
                return cached

            # Acquire a processing lock to reject concurrent duplicates.
            store.acquire_lock(key, ttl=min(ttl, 30))
            try:
                result = fn(*args, **kwargs)
            except Exception:
                store.release_lock(key)
                raise

            # Cache the response when it looks like a structured result.
            if isinstance(result, CachedResponse):
                store.store(key, result, ttl=ttl)
            store.release_lock(key)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
