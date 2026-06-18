"""Redis-backed counters for O(1) aggregates instead of COUNT(*) scans."""

from __future__ import annotations

from kit_core.redis import RedisClient


class Counter:
    """Maintain named integer counters in Redis.

    Reading a maintained counter is O(1), which avoids a ``COUNT(*)`` / ``SUM(...)``
    scan on every request (think like-counts, unread badges, inventory levels).
    Increment on writes and read the running total directly.
    """

    def __init__(self, redis: RedisClient, *, namespace: str = "kit:counter") -> None:
        self._redis = redis
        self._namespace = namespace

    def _key(self, name: str) -> str:
        return f"{self._namespace}:{name}"

    def incr(self, name: str, amount: int = 1) -> int:
        """Increment a counter and return the new value."""
        return int(self._redis.client.incrby(self._key(name), amount))

    def decr(self, name: str, amount: int = 1) -> int:
        """Decrement a counter and return the new value."""
        return int(self._redis.client.decrby(self._key(name), amount))

    def get(self, name: str) -> int:
        """Return the current value (``0`` if unset)."""
        raw = self._redis.client.get(self._key(name))
        return int(raw) if raw is not None else 0

    def get_many(self, names: list[str]) -> dict[str, int]:
        """Return current values for several counters in one round-trip."""
        if not names:
            return {}
        values = self._redis.client.mget([self._key(n) for n in names])
        return {n: int(v) if v is not None else 0 for n, v in zip(names, values, strict=True)}

    def set(self, name: str, value: int) -> None:
        """Set a counter to an exact value."""
        self._redis.client.set(self._key(name), value)

    def reset(self, name: str) -> None:
        """Delete a counter (reads return ``0`` afterward)."""
        self._redis.client.delete(self._key(name))
