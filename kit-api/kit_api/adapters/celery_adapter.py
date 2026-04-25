"""Celery adapter integrating circuit breaker and retry logic with Celery tasks."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Sequence, TypeVar

from kit_core.exceptions import CircuitOpen
from kit_core.redis import RedisClient

from kit_api.circuit_breaker import CircuitBreaker
from kit_api.retry_engine import RetryEngine

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def kit_task(
    *,
    circuit_name: str | None = None,
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: Sequence[type[BaseException]] = (Exception,),
    redis: RedisClient | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps a Celery task function with circuit breaker and
    retry logic from kit-api.

    This should be applied *before* (i.e., below) the ``@app.task`` decorator
    so that the retry and circuit-breaker logic executes inside the Celery
    worker.

    Example::

        @app.task(bind=True)
        @kit_task(circuit_name="payments", max_retries=5)
        def charge_card(self, card_id: str, amount: float) -> dict:
            ...

    Parameters
    ----------
    circuit_name:
        Name for the circuit breaker.  When ``None`` the decorated function's
        qualified name is used.
    failure_threshold:
        Number of consecutive failures before tripping the circuit.
    recovery_timeout:
        Seconds the circuit stays open before transitioning to half-open.
    max_retries:
        Maximum retry attempts (with exponential back-off).
    base_delay:
        Base delay in seconds for exponential back-off.
    max_delay:
        Cap on the computed back-off delay.
    retryable_exceptions:
        Exception types eligible for automatic retry.
    redis:
        Optional ``RedisClient`` instance.
    """

    def decorator(fn: F) -> F:
        _redis = redis or RedisClient()
        _circuit_name = circuit_name or fn.__qualname__

        cb = CircuitBreaker(
            _redis,
            name=_circuit_name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        engine = RetryEngine(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            retryable_exceptions=retryable_exceptions,
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check circuit before attempting execution.
            try:
                cb.allow_request()
            except CircuitOpen:
                logger.error(
                    "Circuit '%s' is open — task %s will not execute",
                    _circuit_name,
                    fn.__qualname__,
                )
                raise

            def _guarded() -> Any:
                try:
                    result = fn(*args, **kwargs)
                except Exception:
                    cb.record_failure()
                    raise
                else:
                    cb.record_success()
                    return result

            return engine.execute(_guarded)

        return wrapper  # type: ignore[return-value]

    return decorator
