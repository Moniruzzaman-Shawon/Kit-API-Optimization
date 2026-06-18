# shawonkit-api

API optimization toolkit providing rate limiting, circuit breaking, retries, idempotency enforcement, and cost tracking. Built on top of `shawonkit-core`.

> Installed as `shawonkit-api`, imported as `kit_api`.

## Installation

```bash
pip install shawonkit-api
```

With framework extras:

```bash
pip install shawonkit-api[django]
pip install shawonkit-api[fastapi]
pip install shawonkit-api[celery]
```

## Usage

### Rate Limiting

```python
from kit_api import RateLimiter, rate_limit
from kit_core.redis import RedisClient

redis = RedisClient()
limiter = RateLimiter(redis, max_requests=100, window_seconds=60)
limiter.acquire("user:42")  # True or raises RateLimitExceeded

@rate_limit(max_requests=10, window=60)
def fetch_data(user_id: str) -> dict:
    ...
```

### Circuit Breaker

```python
from kit_api import CircuitBreaker, circuit_breaker

cb = CircuitBreaker(redis, name="payments", failure_threshold=5, recovery_timeout=30)

@circuit_breaker(name="payments", failure_threshold=5, recovery_timeout=30)
def charge_card(card_id: str, amount: float) -> dict:
    ...
```

### Retry Engine

```python
from kit_api import retry

@retry(max_retries=3, base_delay=1.0)
def call_external_api():
    ...

@retry(max_retries=5, base_delay=0.5)
async def call_external_api_async():
    ...
```

### Idempotency

```python
from kit_api import idempotent

@idempotent(key_func=lambda request: request.headers["Idempotency-Key"])
def create_order(request):
    ...
```

### Cost Tracking

```python
from kit_api import CostTracker, BudgetStatus
from kit_api.cost_tracker import Period

tracker = CostTracker(redis)
tracker.record("openai", "chat/completions", cost=0.03, tokens=1500)
tracker.set_budget("openai", limit=100.0, period=Period.DAILY)
status: BudgetStatus = tracker.check_budget("openai", period=Period.DAILY)
```

### Django Middleware

```python
# settings.py
MIDDLEWARE = [
    "kit_api.middleware.django.KitAPIMiddleware",
    ...
]
KIT_API_RATE_LIMIT_MAX = 100
KIT_API_RATE_LIMIT_WINDOW = 60
```

### FastAPI Middleware

```python
from fastapi import FastAPI
from kit_api.middleware.fastapi import KitAPIMiddleware

app = FastAPI()
app.add_middleware(KitAPIMiddleware, max_requests=100, window_seconds=60)
```

### Celery Integration

```python
from kit_api.adapters.celery_adapter import kit_task

@app.task(bind=True)
@kit_task(circuit_name="payments", max_retries=5)
def charge_card(self, card_id: str, amount: float) -> dict:
    ...
```
