"""Tests for kit_api.retry_engine — no Redis required."""

from __future__ import annotations

import pytest

from kit_api.retry_engine import RetryEngine, retry


class TestRetryEngine:
    def test_succeeds_first_try(self):
        engine = RetryEngine(max_retries=3, base_delay=0)
        result = engine.execute(lambda: 42)
        assert result == 42

    def test_retries_on_failure(self):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        engine = RetryEngine(max_retries=3, base_delay=0, max_delay=0)
        result = engine.execute(flaky)
        assert result == "ok"
        assert call_count == 3

    def test_exhausts_retries(self):
        engine = RetryEngine(max_retries=2, base_delay=0, max_delay=0)
        with pytest.raises(ValueError, match="always fails"):
            engine.execute(lambda: (_ for _ in ()).throw(ValueError("always fails")))

    def test_only_retries_specified_exceptions(self):
        engine = RetryEngine(
            max_retries=3,
            base_delay=0,
            retryable_exceptions=[ValueError],
        )
        # TypeError should not be retried
        with pytest.raises(TypeError):
            engine.execute(lambda: (_ for _ in ()).throw(TypeError("bad type")))

    def test_compute_delay_exponential(self):
        engine = RetryEngine(base_delay=1.0, max_delay=60.0)
        # Delay should increase with attempts (with jitter it's 0..exp)
        for attempt in range(5):
            delay = engine._compute_delay(attempt)
            max_possible = min(60.0, 1.0 * (2 ** attempt))
            assert 0 <= delay <= max_possible


class TestRetryDecorator:
    def test_sync_decorator(self):
        call_count = 0

        @retry(max_retries=2, base_delay=0)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_decorator(self):
        call_count = 0

        @retry(max_retries=2, base_delay=0)
        async def async_flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("fail")
            return "async_success"

        result = await async_flaky()
        assert result == "async_success"
        assert call_count == 2
