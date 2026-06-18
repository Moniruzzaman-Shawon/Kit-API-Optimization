# Kit — Usage Guide & Use Cases

> **What is Kit?** A modular Python toolkit for hardening real-world APIs. It bundles the
> battle-tested patterns you normally re-implement on every backend — rate limiting, circuit
> breaking, retries, idempotency, secure media uploads, CDN routing, and payment/webhook
> handling — into three installable packages backed by Redis for distributed state.

This guide is **problem-oriented**: each section starts with a problem you've probably hit, then
shows the Kit tool that solves it. For the full API reference, see the [README](../README.md);
for per-topic configuration, see [`index.md`](index.md).

---

## Who is this for?

- Teams running a **FastAPI / Django / Celery** backend that talks to flaky third-party APIs.
- Anyone who needs **distributed** versions of these patterns — state shared across multiple
  workers/pods via Redis, not per-process counters that reset on restart.
- Developers who want these guarantees **without** wiring up five separate libraries.

## The mental model

Every Kit component is **stateless in your process** and stores its state in **Redis**. That's
what makes it safe across many workers: two pods enforcing the same rate limit see the same
counter. You pass a Redis client into each component:

```python
from redis import Redis
redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)

# In tests/dev, swap in an in-memory fake — no Redis server needed:
import fakeredis
redis = fakeredis.FakeRedis(decode_responses=True)
```

## Install

```bash
pip install kit-api      # API hardening
pip install kit-media    # uploads, CDN, processing
pip install kit-pay      # payments, webhooks, subscriptions
# kit-core (Redis client, config, logging, exceptions) is pulled in automatically
```

Optional integrations: `kit-api[fastapi]`, `kit-api[django]`, `kit-api[celery]`,
`kit-media[s3|gcs|r2]`, `kit-pay[stripe|paddle]`.

---

## Part 1 — `kit-api`: surviving traffic spikes and flaky upstreams

### Problem: "One client is hammering my API and degrading it for everyone."
**Solution — Rate Limiter** (sliding window, atomic in Redis):

```python
from kit_api.rate_limiter import RateLimiter
from kit_core.exceptions import RateLimitExceeded

limiter = RateLimiter(redis, max_requests=100, window_seconds=60)
try:
    limiter.acquire("user:123")        # raises if over the limit
except RateLimitExceeded as e:
    return 429, {"retry_after": e.retry_after}
```

### Problem: "A downstream service is down and my requests are piling up, taking me down too."
**Solution — Circuit Breaker.** After N failures it "opens" and fails fast instead of hanging,
then probes for recovery — preventing cascading failures:

```python
from kit_api.circuit_breaker import CircuitBreaker
from kit_core.exceptions import CircuitOpen

cb = CircuitBreaker(redis, name="payments-api", failure_threshold=5, recovery_timeout=30)
try:
    cb.allow_request()                 # raises CircuitOpen while the circuit is open
    result = call_external_api()
    cb.record_success()
except Exception:
    cb.record_failure()
    raise
```

### Problem: "Transient network blips cause avoidable failures."
**Solution — Retry Engine** (exponential backoff + jitter, sync or async):

```python
from kit_api.retry_engine import RetryEngine

engine = RetryEngine(max_retries=3, base_delay=1.0, max_delay=60.0,
                     retryable_exceptions=[ConnectionError, TimeoutError])
result = engine.execute(call_flaky_api, arg1, arg2)        # or: await engine.execute_async(...)
```

### Problem: "A retried POST charged the customer twice."
**Solution — Idempotency Store.** Cache the first response per idempotency key and replay it for
duplicates, with a lock to stop concurrent double-processing:

```python
from kit_api.idempotency import IdempotencyStore, CachedResponse

store = IdempotencyStore(redis)
if cached := store.check("order-key-abc"):
    return cached.body
store.acquire_lock("order-key-abc")
store.store("order-key-abc", CachedResponse(status_code=200, body=process_order(), headers={}), ttl=3600)
```

### Problem: "My OpenAI/Stripe bill surprised me at month end."
**Solution — Cost Tracker** with per-provider budgets:

```python
from kit_api.cost_tracker import CostTracker, Period

tracker = CostTracker(redis)
tracker.record("openai", "chat/completions", cost=0.03, tokens=1500)
tracker.set_budget("openai", limit=50.0, period=Period.DAILY)
status = tracker.check_budget("openai", Period.DAILY)      # used / remaining / percentage
```

**Zero-code option:** drop in the framework middleware to apply rate limiting + idempotency to
every route — `kit_api.middleware.fastapi.KitAPIMiddleware`,
`kit_api.middleware.django.KitAPIMiddleware`, or wrap Celery tasks with
`kit_api.adapters.celery_adapter.kit_task`.

---

## Part 2 — `kit-media`: uploads and delivery without proxying bytes

### Problem: "Large uploads flow through my app server and exhaust it."
**Solution — Presigned URLs.** Clients upload directly to S3/R2/GCS; your server only signs:

```python
from kit_media import PresignedURLGenerator
from kit_media.adapters.s3_adapter import S3Adapter

gen = PresignedURLGenerator(adapter=S3Adapter(region="us-east-1"))
upload = await gen.generate_upload_url(bucket="my-bucket", key="uploads/photo.jpg",
                                       content_type="image/jpeg", expires=3600)
```

### Problem: "Multi-GB uploads fail halfway with no resume."
**Solution — Chunked Uploader** with progress tracked in Redis (`initiate` → `upload_part` →
`get_progress` → `complete`/`abort`).

### Problem: "Users worldwide get slow downloads from a single origin."
**Solution — CDN Router** picks the best endpoint by region + weighted load balancing, with
signed URLs and cache purging:

```python
from kit_media import CDNRouter, CDNEndpoint

router = CDNRouter(endpoints=[
    CDNEndpoint(name="eu", base_url="https://eu.cdn.example.com", regions=["eu", "uk"], weight=2),
    CDNEndpoint(name="us", base_url="https://us.cdn.example.com", regions=["us"], weight=3),
])
url = router.resolve("images/hero.jpg", region="eu")
```

### Also in `kit-media`
- **Media Processor** — build CDN transform URLs (resize/format/quality) and validate MIME types.
- **Caption Job** — manage async transcription/captioning jobs with Redis state.

---

## Part 3 — `kit-pay`: payments, webhooks, and subscriptions done safely

### Problem: "A provider sent the same webhook twice and I processed it twice."
**Solution — Webhook Receiver**: HMAC signature verification, normalization across providers
(Stripe/Paddle), handler registration, and **automatic deduplication by event ID**:

```python
from kit_pay import WebhookReceiver

receiver = WebhookReceiver(redis)
if not receiver.verify(raw_body, signature, secret="whsec_..."):
    raise Unauthorized()
event = receiver.parse(raw_body, provider="stripe")
receiver.register_handler("invoice.paid", activate_subscription)
result = receiver.process(event)            # SUCCESS / SKIPPED (duplicate) / FAILED
```

### Problem: "My subscription states are a tangle of booleans."
**Solution — Plan State Manager**: subscriptions as a finite state machine with enforced,
validated transitions (`TRIAL → ACTIVE → PAST_DUE → GRACE → …`), plus a **Grace Handler** for
dunning/grace periods with reminders.

### Problem: "I need to stop charging a customer once they hit a spend cap."
**Solution — Budget Enforcer**: per-customer limits that block over-budget charges and keep an
auditable history. There's also an **Event Processor** (queue + retry + dead-letter) and an
**Idempotency Key Manager** to prevent duplicate charges.

---

## Putting it together

A runnable FastAPI app demonstrating all three packages lives in
[`example-app/main.py`](../example-app/main.py):

```bash
cd Kit-API-Optimization
pip install fastapi uvicorn fakeredis redis pydantic pydantic-settings structlog httpx
PYTHONPATH=kit-core:kit-api:kit-media:kit-pay:example-app \
  python -m uvicorn main:app --reload --port 8000
# open http://localhost:8000/docs
```

## Testing your integration

Kit is built to be testable **without** a Redis server — every component accepts a `redis`
argument, so pass `fakeredis.FakeRedis()` in tests:

```bash
pip install pytest pytest-asyncio fakeredis
PYTHONPATH=kit-core:kit-api:kit-media:kit-pay \
  pytest kit-core/tests kit-api/tests kit-media/tests kit-pay/tests -v \
  --override-ini="asyncio_mode=auto"
```

## Configuration

All packages read `KIT_`-prefixed env vars (`KIT_REDIS_URL`, `KIT_LOG_LEVEL`,
`KIT_ENVIRONMENT`, `KIT_DEBUG`). See [`index.md`](index.md) for the table and defaults.

## Where to go next

- **API reference:** [`README.md`](../README.md) — every class, method, and parameter.
- **Per-package docs:** [`index.md`](index.md).
- **Source & issues:** <https://github.com/Moniruzzaman-Shawon/Kit-API-Optimization>
