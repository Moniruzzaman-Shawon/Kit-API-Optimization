"""Retry engine with exponential backoff, jitter, and async support."""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, Sequence, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RetryEngine:
    """Execute a callable with configurable retry behaviour.

    Uses exponential backoff with full jitter:
        ``delay = random.uniform(0, min(max_delay, base_delay * 2 ** attempt))``
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        retryable_exceptions: Sequence[type[BaseException]] = (Exception,),
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retryable_exceptions = tuple(retryable_exceptions)

    def _compute_delay(self, attempt: int) -> float:
        exp = min(self.max_delay, self.base_delay * (2 ** attempt))
        return random.uniform(0, exp)

    def _log_retry(self, fn_name: str, attempt: int, delay: float, exc: BaseException) -> None:
        logger.warning(
            "Retry attempt %d/%d for %s after %.2fs — %s: %s",
            attempt,
            self.max_retries,
            fn_name,
            delay,
            type(exc).__name__,
            exc,
        )

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* synchronously with retries."""
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except self.retryable_exceptions as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                delay = self._compute_delay(attempt)
                self._log_retry(getattr(fn, "__qualname__", str(fn)), attempt + 1, delay, exc)
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def execute_async(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute an async callable with retries."""
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except self.retryable_exceptions as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                delay = self._compute_delay(attempt)
                self._log_retry(getattr(fn, "__qualname__", str(fn)), attempt + 1, delay, exc)
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    *,
    max_delay: float = 60.0,
    retryable_exceptions: Sequence[type[BaseException]] = (Exception,),
) -> Callable[[F], F]:
    """Decorator that retries the wrapped function on failure.

    Supports both sync and async callables.
    """

    def decorator(fn: F) -> F:
        engine = RetryEngine(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            retryable_exceptions=retryable_exceptions,
        )

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await engine.execute_async(fn, *args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return engine.execute(fn, *args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
