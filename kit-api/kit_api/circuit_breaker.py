"""Distributed circuit breaker backed by Redis."""

from __future__ import annotations

import enum
import functools
import time
from typing import Any, Callable, TypeVar

from kit_core.exceptions import CircuitOpen
from kit_core.redis import RedisClient

F = TypeVar("F", bound=Callable[..., Any])


class State(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Distributed circuit breaker storing state in Redis.

    State transitions:
        CLOSED  -> OPEN       when consecutive failures >= *failure_threshold*
        OPEN    -> HALF_OPEN  after *recovery_timeout* seconds
        HALF_OPEN -> CLOSED   if a trial call succeeds
        HALF_OPEN -> OPEN     if a trial call fails
    """

    def __init__(
        self,
        redis: RedisClient,
        *,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 1,
    ) -> None:
        self._redis = redis
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

    # -- Redis key helpers ---------------------------------------------------

    def _key(self, suffix: str) -> str:
        return f"kit:cb:{self.name}:{suffix}"

    @property
    def _state_key(self) -> str:
        return self._key("state")

    @property
    def _failures_key(self) -> str:
        return self._key("failures")

    @property
    def _opened_at_key(self) -> str:
        return self._key("opened_at")

    @property
    def _half_open_calls_key(self) -> str:
        return self._key("ho_calls")

    # -- State management ----------------------------------------------------

    def _get_state(self) -> State:
        raw = self._redis.client.get(self._state_key)
        if raw is None:
            return State.CLOSED
        value = raw.decode() if isinstance(raw, bytes) else raw
        return State(value)

    def _set_state(self, state: State) -> None:
        self._redis.client.set(self._state_key, state.value)

    def _get_int(self, key: str) -> int:
        val = self._redis.client.get(key)
        if val is None:
            return 0
        return int(val)

    # -- Public API ----------------------------------------------------------

    @property
    def state(self) -> State:
        """Return the current circuit state, promoting OPEN -> HALF_OPEN when
        the recovery timeout has elapsed."""
        current = self._get_state()
        if current is State.OPEN:
            opened_at = self._get_int(self._opened_at_key)
            if time.time() - opened_at >= self.recovery_timeout:
                self._set_state(State.HALF_OPEN)
                self._redis.client.set(self._half_open_calls_key, 0)
                return State.HALF_OPEN
        return current

    def record_success(self) -> None:
        """Record a successful call."""
        state = self.state
        if state is State.HALF_OPEN:
            self._set_state(State.CLOSED)
            self._redis.client.set(self._failures_key, 0)
            self._redis.client.delete(self._half_open_calls_key)
        elif state is State.CLOSED:
            self._redis.client.set(self._failures_key, 0)

    def record_failure(self) -> None:
        """Record a failed call."""
        state = self.state
        if state is State.HALF_OPEN:
            self._trip()
        elif state is State.CLOSED:
            failures = self._redis.client.incr(self._failures_key)
            if failures >= self.failure_threshold:
                self._trip()

    def _trip(self) -> None:
        self._set_state(State.OPEN)
        self._redis.client.set(self._opened_at_key, int(time.time()))

    def allow_request(self) -> bool:
        """Return ``True`` if a request may proceed, raise ``CircuitOpen``
        otherwise."""
        state = self.state
        if state is State.CLOSED:
            return True
        if state is State.HALF_OPEN:
            calls = self._redis.client.incr(self._half_open_calls_key)
            if calls <= self.half_open_max_calls:
                return True
            raise CircuitOpen(f"Circuit '{self.name}' is half-open and trial limit reached")
        raise CircuitOpen(f"Circuit '{self.name}' is open")

    def reset(self) -> None:
        """Force-reset the circuit to CLOSED."""
        pipe = self._redis.client.pipeline()
        pipe.delete(self._state_key, self._failures_key, self._opened_at_key, self._half_open_calls_key)
        pipe.execute()


def circuit_breaker(
    name: str,
    *,
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
    half_open_max_calls: int = 1,
    redis: RedisClient | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps a function with circuit-breaker protection."""

    def decorator(fn: F) -> F:
        _redis = redis or RedisClient()
        cb = CircuitBreaker(
            _redis,
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb.allow_request()
            try:
                result = fn(*args, **kwargs)
            except Exception:
                cb.record_failure()
                raise
            else:
                cb.record_success()
                return result

        return wrapper  # type: ignore[return-value]

    return decorator
