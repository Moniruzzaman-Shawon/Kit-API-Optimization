from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from redis import Redis


class IdempotencyKeyManager:
    """Manages idempotency keys for payment operations to prevent duplicate charges."""

    def __init__(self, redis: Redis, prefix: str = "kit:idempotency") -> None:
        self._redis = redis
        self._prefix = prefix

    def generate(self, operation: str, *identifiers: str) -> str:
        """Generate a deterministic idempotency key from operation name and identifiers."""
        raw = f"{operation}:{':'.join(identifiers)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def acquire_lock(self, key: str, ttl: int = 300) -> bool:
        """Acquire a distributed lock for the given idempotency key.

        Returns True if the lock was acquired, False if the key is already locked
        (meaning another process is handling this operation).
        """
        lock_key = f"{self._prefix}:lock:{key}"
        acquired = self._redis.set(lock_key, time.time(), nx=True, ex=ttl)
        return bool(acquired)

    def release_lock(self, key: str) -> None:
        """Release the distributed lock for the given idempotency key."""
        lock_key = f"{self._prefix}:lock:{key}"
        self._redis.delete(lock_key)

    def mark_completed(
        self, key: str, result: dict[str, Any], ttl: int = 86400
    ) -> None:
        """Mark an operation as completed and store its result.

        The result is retained for ``ttl`` seconds so that replayed requests
        can return the cached outcome instead of executing again.
        """
        result_key = f"{self._prefix}:result:{key}"
        payload = json.dumps(
            {"result": result, "completed_at": time.time()},
        )
        self._redis.set(result_key, payload, ex=ttl)
        self.release_lock(key)

    def get_result(self, key: str) -> dict[str, Any] | None:
        """Retrieve the stored result for a previously completed operation.

        Returns None if no result has been recorded for the key.
        """
        result_key = f"{self._prefix}:result:{key}"
        raw = self._redis.get(result_key)
        if raw is None:
            return None
        data = json.loads(raw)
        return data["result"]
