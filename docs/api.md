# kit-api — API optimization

Tools for hardening an API against overload, failures, and duplicate requests. All state is
stored in Redis, so guarantees hold across multiple workers/pods.

**Install:** `pip install kit-api` (optional: `kit-api[fastapi]`, `kit-api[django]`, `kit-api[celery]`)

← Back to [docs index](index.md) · Problem-oriented walkthrough in the [Usage Guide](guide.md) ·
Full reference in the [README](../README.md)

## Components

| Component | Module | Solves |
|-----------|--------|--------|
| `RateLimiter` | `kit_api.rate_limiter` | Sliding-window rate limiting (atomic Lua script) |
| `CircuitBreaker` | `kit_api.circuit_breaker` | Fail-fast when a dependency is down; auto-recovery |
| `RetryEngine` | `kit_api.retry_engine` | Exponential backoff + jitter (sync & async) |
| `IdempotencyStore` | `kit_api.idempotency` | Replay cached responses; prevent double-processing |
| `CostTracker` | `kit_api.cost_tracker` | Per-provider cost accounting and budgets |

## Minimal examples

```python
from kit_api.rate_limiter import RateLimiter
RateLimiter(redis, max_requests=100, window_seconds=60).acquire("user:123")

from kit_api.circuit_breaker import CircuitBreaker
cb = CircuitBreaker(redis, name="payments-api", failure_threshold=5, recovery_timeout=30)

from kit_api.retry_engine import RetryEngine
RetryEngine(max_retries=3, base_delay=1.0).execute(call_flaky_api)

from kit_api.idempotency import IdempotencyStore
store = IdempotencyStore(redis)

from kit_api.cost_tracker import CostTracker, Period
CostTracker(redis).record("openai", "chat/completions", cost=0.03, tokens=1500)
```

## Framework integration

- **FastAPI / Django:** `kit_api.middleware.fastapi.KitAPIMiddleware`,
  `kit_api.middleware.django.KitAPIMiddleware` apply rate limiting + idempotency to every route.
- **Celery:** wrap tasks with `kit_api.adapters.celery_adapter.kit_task` for circuit breaking + retry.

See the [README](../README.md#package-1-kit-api--api-optimization) for full parameters and decorators.
