"""Redis adapter specialised for kit-api operations."""

from __future__ import annotations

from typing import Any

from kit_core.redis import RedisClient


class KitAPIRedisAdapter:
    """Thin wrapper around :class:`kit_core.redis.RedisClient` that provides
    convenience helpers for the data structures used by kit-api (rate-limit
    windows, circuit-breaker state, idempotency keys, and cost buckets).
    """

    def __init__(self, redis: RedisClient | None = None, *, url: str | None = None) -> None:
        self._redis = redis or RedisClient(url=url)

    @property
    def client(self) -> Any:
        """Return the underlying Redis client for direct access."""
        return self._redis.client

    # -- Rate limiting helpers -----------------------------------------------

    def get_rate_limit_keys(self, prefix: str = "kit:rl") -> list[str]:
        """Return all rate-limit keys matching *prefix*."""
        return [
            k.decode() if isinstance(k, bytes) else k
            for k in self._redis.client.keys(f"{prefix}:*")
        ]

    def flush_rate_limits(self, prefix: str = "kit:rl") -> int:
        """Delete all rate-limit keys. Returns count deleted."""
        keys = self._redis.client.keys(f"{prefix}:*")
        if not keys:
            return 0
        return self._redis.client.delete(*keys)

    # -- Circuit breaker helpers ---------------------------------------------

    def get_circuit_state(self, name: str) -> dict[str, Any]:
        """Return a snapshot of the circuit breaker state for *name*."""
        prefix = f"kit:cb:{name}"
        pipe = self._redis.client.pipeline()
        pipe.get(f"{prefix}:state")
        pipe.get(f"{prefix}:failures")
        pipe.get(f"{prefix}:opened_at")
        state_raw, failures_raw, opened_at_raw = pipe.execute()

        def _decode(v: Any) -> str | None:
            if v is None:
                return None
            return v.decode() if isinstance(v, bytes) else str(v)

        return {
            "name": name,
            "state": _decode(state_raw) or "closed",
            "failures": int(failures_raw) if failures_raw else 0,
            "opened_at": int(opened_at_raw) if opened_at_raw else None,
        }

    def reset_circuit(self, name: str) -> None:
        """Force-reset all Redis keys for circuit *name*."""
        prefix = f"kit:cb:{name}"
        keys = self._redis.client.keys(f"{prefix}:*")
        if keys:
            self._redis.client.delete(*keys)

    # -- Idempotency helpers -------------------------------------------------

    def get_idempotency_keys(self, prefix: str = "kit:idem") -> list[str]:
        """Return all current idempotency keys."""
        return [
            k.decode() if isinstance(k, bytes) else k
            for k in self._redis.client.keys(f"{prefix}:*")
        ]

    def flush_idempotency(self, prefix: str = "kit:idem") -> int:
        """Delete all idempotency keys. Returns count deleted."""
        keys = self._redis.client.keys(f"{prefix}:*")
        if not keys:
            return 0
        return self._redis.client.delete(*keys)

    # -- Cost tracking helpers -----------------------------------------------

    def get_cost_keys(self, prefix: str = "kit:cost") -> list[str]:
        """Return all cost-tracking keys."""
        return [
            k.decode() if isinstance(k, bytes) else k
            for k in self._redis.client.keys(f"{prefix}:*")
        ]

    def flush_costs(self, prefix: str = "kit:cost") -> int:
        """Delete all cost-tracking keys. Returns count deleted."""
        keys = self._redis.client.keys(f"{prefix}:*")
        if not keys:
            return 0
        return self._redis.client.delete(*keys)

    def flush_all(self) -> dict[str, int]:
        """Flush all kit-api keys and return per-category deletion counts."""
        return {
            "rate_limits": self.flush_rate_limits(),
            "circuits": len(self._flush_prefix("kit:cb")),
            "idempotency": self.flush_idempotency(),
            "costs": self.flush_costs(),
        }

    def _flush_prefix(self, prefix: str) -> list[str]:
        keys = self._redis.client.keys(f"{prefix}:*")
        if keys:
            self._redis.client.delete(*keys)
        return [k.decode() if isinstance(k, bytes) else k for k in keys]
