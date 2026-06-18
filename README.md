# Kit — API Optimization Toolkit

A modular Python monorepo with **three production-grade packages** for API rate limiting, media handling, and payment processing. Each package is independently installable, backed by Redis for distributed state, and comes with framework integrations for **FastAPI** and **Django**.

---

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Package 1: kit-api — API Optimization](#package-1-kit-api--api-optimization)
  - [Rate Limiter](#1-rate-limiter)
  - [Circuit Breaker](#2-circuit-breaker)
  - [Retry Engine](#3-retry-engine)
  - [Idempotency Store](#4-idempotency-store)
  - [Cost Tracker](#5-cost-tracker)
  - [Framework Middleware](#6-framework-middleware)
- [Package 2: kit-media — Media Handling](#package-2-kit-media--media-handling)
  - [Presigned URL Generator](#1-presigned-url-generator)
  - [Chunked Uploader](#2-chunked-uploader)
  - [CDN Router](#3-cdn-router)
  - [Media Processor](#4-media-processor)
  - [Caption Job](#5-caption-job)
- [Package 3: kit-pay — Payment Processing](#package-3-kit-pay--payment-processing)
  - [Idempotency Key Manager](#1-idempotency-key-manager)
  - [Webhook Receiver](#2-webhook-receiver)
  - [Event Processor](#3-event-processor)
  - [Plan State Manager](#4-plan-state-manager)
  - [Grace Handler](#5-grace-handler)
  - [Budget Enforcer](#6-budget-enforcer)
- [Shared: kit-core](#shared-kit-core)
- [Example App](#example-app)
- [Running Tests](#running-tests)
- [Configuration](#configuration)

---

## Architecture

```
kit-core (shared: Redis client, config, structured logging, exceptions)
  ├── kit-api     pip install kit-api
  ├── kit-media   pip install kit-media
  └── kit-pay     pip install kit-pay
```

All three packages depend on `kit-core` (auto-installed). Each uses Redis for distributed state management — rate limit counters, circuit breaker state, upload progress, subscription state, etc.

## Quick Start

### Requirements

- Python 3.10+
- Redis server (or use `fakeredis` for development/testing)

### Installation

```bash
# Install individual packages (kit-core is auto-installed as dependency)
pip install kit-api
pip install kit-media
pip install kit-pay

# Or install everything at once
pip install kit

# With optional provider adapters
pip install kit-api[fastapi]          # FastAPI middleware
pip install kit-api[django]           # Django middleware
pip install kit-api[celery]           # Celery integration
pip install kit-media[s3]             # AWS S3 adapter
pip install kit-media[gcs]            # Google Cloud Storage adapter
pip install kit-media[r2]             # Cloudflare R2 adapter
pip install kit-pay[stripe]           # Stripe adapter
pip install kit-pay[paddle]           # Paddle adapter
```

### Connect to Redis

```python
from redis import Redis

redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)
```

All kit components accept a `redis` parameter in their constructor. In production, point this to your Redis instance. For development, use `fakeredis`:

```python
import fakeredis
redis = fakeredis.FakeRedis(decode_responses=True)
```

---

## Package 1: kit-api — API Optimization

**Install:** `pip install kit-api`

Five tools for hardening your API against overload, failures, and duplicate requests.

### 1. Rate Limiter

Sliding-window rate limiter using Redis sorted sets with an atomic Lua script.

```python
from kit_api.rate_limiter import RateLimiter

# Create a limiter: 100 requests per 60-second window
limiter = RateLimiter(redis, max_requests=100, window_seconds=60)

# Check if a request is allowed (raises RateLimitExceeded if not)
limiter.acquire("user:123")

# Check remaining quota
remaining = limiter.remaining("user:123")  # e.g., 97

# Reset a key
limiter.reset("user:123")
```

**As a decorator:**

```python
from kit_api.rate_limiter import rate_limit

@rate_limit(max_requests=10, window=60, key_func=lambda user_id: f"user:{user_id}")
def get_profile(user_id: str):
    return fetch_profile(user_id)
```

**What happens when the limit is exceeded:**

```python
from kit_core.exceptions import RateLimitExceeded

try:
    limiter.acquire("user:123")
except RateLimitExceeded as e:
    print(f"Try again in {e.retry_after} seconds")
```

### 2. Circuit Breaker

Distributed circuit breaker that stores state in Redis, preventing cascading failures when an external service goes down.

**States:** `CLOSED` (normal) → `OPEN` (blocking) → `HALF_OPEN` (testing recovery)

```python
from kit_api.circuit_breaker import CircuitBreaker

cb = CircuitBreaker(
    redis,
    name="payments-api",
    failure_threshold=5,      # open after 5 failures
    recovery_timeout=30,      # try again after 30s
    half_open_max_calls=1,    # allow 1 test call in half-open
)

# Check state
state = cb.state  # State.CLOSED, State.OPEN, or State.HALF_OPEN

# Use in your code
cb.allow_request()  # raises CircuitOpen if circuit is open
try:
    result = call_external_api()
    cb.record_success()
except Exception:
    cb.record_failure()  # increments failure counter
    raise

# Force reset
cb.reset()
```

**As a decorator:**

```python
from kit_api.circuit_breaker import circuit_breaker

@circuit_breaker(name="email-service", failure_threshold=3, recovery_timeout=60)
def send_email(to: str, body: str):
    return email_client.send(to, body)
```

### 3. Retry Engine

Exponential backoff with full jitter. Supports both sync and async functions.

```python
from kit_api.retry_engine import RetryEngine

engine = RetryEngine(
    max_retries=3,
    base_delay=1.0,       # starts at 1s
    max_delay=60.0,        # caps at 60s
    retryable_exceptions=[ConnectionError, TimeoutError],
)

# Sync
result = engine.execute(call_flaky_api, arg1, arg2)

# Async
result = await engine.execute_async(async_call, arg1)
```

**As a decorator:**

```python
from kit_api.retry_engine import retry

@retry(max_retries=3, base_delay=0.5)
def fetch_data():
    return requests.get("https://api.example.com/data").json()

@retry(max_retries=5, base_delay=1.0, retryable_exceptions=[TimeoutError])
async def async_fetch():
    return await httpx.get("https://api.example.com/data")
```

### 4. Idempotency Store

Prevents duplicate processing of the same request using Redis-backed fingerprinting.

```python
from kit_api.idempotency import IdempotencyStore, CachedResponse

store = IdempotencyStore(redis)

# Check if we've seen this key before
cached = store.check("order-key-abc")
if cached:
    return cached.body  # return the previously stored response

# Acquire a lock (prevents concurrent processing of the same key)
store.acquire_lock("order-key-abc")

# Process and store the result
result = process_order()
store.store("order-key-abc", CachedResponse(
    status_code=200,
    body=result,
    headers={},
), ttl=3600)
```

**As a decorator:**

```python
from kit_api.idempotency import idempotent

@idempotent(key_func=lambda request: request.headers["Idempotency-Key"])
def create_order(request):
    return {"order_id": "ord_123", "status": "created"}
```

### 5. Cost Tracker

Track per-provider, per-endpoint API costs with budget enforcement.

```python
from kit_api.cost_tracker import CostTracker, Period

tracker = CostTracker(redis)

# Record a cost
tracker.record("openai", "chat/completions", cost=0.03, tokens=1500)
tracker.record("openai", "embeddings", cost=0.001, tokens=500)

# Check usage
usage = tracker.get_usage("openai", Period.DAILY)      # total cost today
ep_usage = tracker.get_endpoint_usage("openai", "chat/completions", Period.DAILY)

# Set and check budgets
tracker.set_budget("openai", limit=50.0, period=Period.DAILY)
status = tracker.check_budget("openai", Period.DAILY)
print(f"Used: ${status.used}, Remaining: ${status.remaining}, {status.percentage}%")
```

### 6. Framework Middleware

**FastAPI** — automatically applies rate limiting + idempotency to all routes:

```python
from fastapi import FastAPI
from kit_api.middleware.fastapi import KitAPIMiddleware

app = FastAPI()
app.add_middleware(
    KitAPIMiddleware,
    max_requests=100,       # per client IP
    window_seconds=60,
    idempotency_ttl=3600,
)
```

**Django** — add to `settings.py`:

```python
MIDDLEWARE = [
    "kit_api.middleware.django.KitAPIMiddleware",
    # ... other middleware
]

# Optional settings
KIT_RATE_LIMIT_MAX_REQUESTS = 100
KIT_RATE_LIMIT_WINDOW = 60
KIT_IDEMPOTENCY_TTL = 3600
```

**Celery** — wrap tasks with circuit breaker + retry:

```python
from celery import Celery
from kit_api.adapters.celery_adapter import kit_task

app = Celery("myapp")

@app.task
@kit_task(circuit_name="payment-service", max_retries=3)
def process_payment(payment_id: str):
    return charge(payment_id)
```

---

## Package 2: kit-media — Media Handling

**Install:** `pip install kit-media`

Five tools for file uploads, CDN delivery, and media processing.

### 1. Presigned URL Generator

Generate secure, time-limited URLs for direct uploads/downloads to cloud storage.

```python
from kit_media import PresignedURLGenerator
from kit_media.adapters.s3_adapter import S3Adapter

adapter = S3Adapter(region="us-east-1")
generator = PresignedURLGenerator(adapter=adapter)

# Generate upload URL (returns URL + form fields for POST upload)
upload = await generator.generate_upload_url(
    bucket="my-bucket",
    key="uploads/photo.jpg",
    content_type="image/jpeg",
    expires=3600,  # 1 hour
)
print(upload.url)        # presigned URL
print(upload.fields)     # form fields to include in POST
print(upload.expires_at) # expiry timestamp

# Generate download URL
download_url = await generator.generate_download_url(
    bucket="my-bucket",
    key="uploads/photo.jpg",
    filename="photo.jpg",  # triggers download in browser
)
```

**Supported adapters:**

```python
from kit_media.adapters.s3_adapter import S3Adapter    # AWS S3
from kit_media.adapters.r2_adapter import R2Adapter    # Cloudflare R2
from kit_media.adapters.gcs_adapter import GCSAdapter  # Google Cloud Storage

# Cloudflare R2
r2 = R2Adapter(
    account_id="your-account-id",
    access_key_id="your-key",
    secret_access_key="your-secret",
)

# Google Cloud Storage
gcs = GCSAdapter(project="my-project", credentials_path="/path/to/creds.json")
```

### 2. Chunked Uploader

Multipart uploads with progress tracking in Redis.

```python
from kit_media import ChunkedUploader

uploader = ChunkedUploader(adapter=s3_adapter, redis=redis_client)

# Start upload
upload_id = await uploader.initiate("my-bucket", "large-file.zip", "application/zip")

# Upload parts (typically in a loop reading file chunks)
etag1 = await uploader.upload_part(upload_id, part_number=1, data=chunk1)
etag2 = await uploader.upload_part(upload_id, part_number=2, data=chunk2)

# Check progress
progress = await uploader.get_progress(upload_id)
print(f"{progress.completed_parts} of {progress.total_parts} parts uploaded")

# Complete
location = await uploader.complete(upload_id)

# Or abort
await uploader.abort(upload_id)
```

### 3. CDN Router

Intelligent CDN URL routing based on region and weighted load balancing.

```python
from kit_media import CDNRouter, CDNEndpoint

router = CDNRouter(endpoints=[
    CDNEndpoint(name="us-primary", base_url="https://us.cdn.example.com", regions=["us", "ca"], weight=3),
    CDNEndpoint(name="eu-primary", base_url="https://eu.cdn.example.com", regions=["eu", "uk"], weight=2),
    CDNEndpoint(name="ap-fallback", base_url="https://ap.cdn.example.com", regions=["ap"], weight=1),
])

# Resolve best URL for a user's region
url = router.resolve("images/hero.jpg", region="eu")
# → "https://eu.cdn.example.com/images/hero.jpg"

# Get URLs from all CDNs
all_urls = router.resolve_all("images/hero.jpg")

# Signed URLs for private content
private_cdn = CDNEndpoint(
    name="private",
    base_url="https://secure.cdn.example.com",
    signing_key="your-secret-key",
)
# URL will include ?expires=...&sig=... parameters

# Cache invalidation
await router.purge("images/hero.jpg")
await router.purge_prefix("images/")
```

### 4. Media Processor

Build CDN transformation URLs and validate media types.

```python
from kit_media import MediaProcessor, TransformSpec, FitMode

processor = MediaProcessor(transform_base_url="https://images.example.com/transform")

# Build a transform URL
spec = TransformSpec(width=800, height=600, format="webp", quality=80, fit=FitMode.COVER)
url = processor.build_transform_url("https://cdn.example.com/photo.jpg", spec)
# → "https://images.example.com/transform/?w=800&h=600&fm=webp&q=80&fit=cover&url=..."

# Validate upload MIME types
processor.validate_media_type("image/jpeg")       # True
processor.validate_media_type("application/json")  # False

# Get image dimensions (requires Pillow)
width, height = processor.get_dimensions("/path/to/image.jpg")
```

### 5. Caption Job

Manage async media captioning/transcription jobs with Redis state tracking.

```python
from kit_media import CaptionJob, JobStatus

captions = CaptionJob(redis=redis_client)

# Submit a job
job_id = await captions.submit("https://example.com/video.mp4", language="en")

# Poll status
status = await captions.poll(job_id)  # JobStatus.PENDING / PROCESSING / COMPLETED / FAILED

# Get result when complete
result = await captions.get_result(job_id)
print(result.text)                    # full transcript
print(result.language)                # detected language
for segment in result.segments:
    print(f"[{segment.start:.1f}s - {segment.end:.1f}s] {segment.text}")
```

---

## Package 3: kit-pay — Payment Processing

**Install:** `pip install kit-pay`

Six tools for handling payments, webhooks, subscriptions, and budgets.

### 1. Idempotency Key Manager

Prevent duplicate charges with deterministic key generation and distributed locking.

```python
from kit_pay import IdempotencyKeyManager

manager = IdempotencyKeyManager(redis)

# Generate a deterministic key
key = manager.generate("charge", "cust_123", "inv_456")

# Acquire a distributed lock
if manager.acquire_lock(key, ttl=300):
    try:
        result = process_payment()
        manager.mark_completed(key, result, ttl=86400)
    finally:
        manager.release_lock(key)

# Check if already processed
previous = manager.get_result(key)
if previous:
    return previous  # skip duplicate processing
```

### 2. Webhook Receiver

Secure webhook handling with signature verification, event normalization, and deduplication.

```python
from kit_pay import WebhookReceiver

receiver = WebhookReceiver(redis)

# 1. Verify signature (HMAC-SHA256)
is_valid = receiver.verify(
    payload=raw_body,
    signature=request.headers["X-Webhook-Signature"],
    secret="whsec_your_secret",
)

# 2. Parse into normalized event (works with Stripe, Paddle, etc.)
event = receiver.parse(raw_body, provider="stripe")
print(event.id, event.type, event.provider, event.timestamp)

# 3. Register handlers
def handle_invoice_paid(event):
    activate_subscription(event.data)

def handle_subscription_cancelled(event):
    deactivate_account(event.data)

receiver.register_handler("invoice.paid", handle_invoice_paid)
receiver.register_handler("customer.subscription.deleted", handle_subscription_cancelled)

# 4. Process (auto-deduplicates by event ID)
result = receiver.process(event)
print(result.status)  # ProcessStatus.SUCCESS / SKIPPED / FAILED
```

**In a FastAPI endpoint:**

```python
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not receiver.verify(body, sig, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = receiver.parse(body, provider="stripe")
    result = receiver.process(event)
    return {"status": result.status.value}
```

### 3. Event Processor

Async event processing pipeline with retry and dead-letter queue.

```python
from kit_pay import EventProcessor

processor = EventProcessor(redis)

# Enqueue events
processor.enqueue(event)

# Batch process
results = processor.process_batch(max_events=100)

# Retry failed events
processor.retry_failed()
```

### 4. Plan State Manager

Subscription lifecycle as a finite state machine with enforced transitions.

```python
from kit_pay import PlanStateManager, PlanState, Subscription

plans = PlanStateManager(redis)

# Create a subscription
sub = Subscription(
    id="sub_001",
    customer_id="cust_123",
    plan_id="plan_pro",
    state=PlanState.TRIAL,
    current_period_end=1735689600.0,
)
plans.create(sub)

# Transition states (validates allowed transitions)
plans.transition("sub_001", PlanState.ACTIVE)       # TRIAL → ACTIVE ✓
plans.transition("sub_001", PlanState.PAST_DUE)     # ACTIVE → PAST_DUE ✓
plans.transition("sub_001", PlanState.TRIAL)         # ACTIVE → TRIAL ✗ raises InvalidTransitionError

# Check access
plans.is_active("sub_001")  # True for TRIAL, ACTIVE, PAST_DUE, GRACE
```

**Valid state transitions:**

```
TRIAL     → ACTIVE, CANCELLED, EXPIRED
ACTIVE    → PAST_DUE, CANCELLED, EXPIRED
PAST_DUE  → ACTIVE, GRACE, CANCELLED
GRACE     → ACTIVE, CANCELLED, EXPIRED
CANCELLED → ACTIVE (reactivation)
EXPIRED   → ACTIVE (reactivation)
```

### 5. Grace Handler

Manage payment grace periods with configurable duration and reminders.

```python
from kit_pay import GraceHandler

grace = GraceHandler(redis, plan_manager=plans, grace_days=7, reminder_intervals=[1, 3, 5])

# Start grace period
period = grace.start_grace("sub_001", reason="payment_failed")
print(period.ends_at)  # 7 days from now

# Check grace
active_grace = grace.check_grace("sub_001")
if active_grace:
    print(f"Grace ends: {active_grace.ends_at}")

# Extend if needed
grace.extend_grace("sub_001", days=3)

# End grace (with state transition)
grace.end_grace("sub_001", reason="payment_received")
```

### 6. Budget Enforcer

Per-customer spending limits that block charges exceeding the budget.

```python
from kit_pay import BudgetEnforcer

enforcer = BudgetEnforcer(redis)

# Set a spending limit
enforcer.set_limit("cust_123", amount=100.0, period="monthly")

# Record charges (raises PaymentError if over budget)
enforcer.record_charge("cust_123", amount=40.0, description="March API usage")
enforcer.record_charge("cust_123", amount=50.0, description="March compute")

# This would raise PaymentError: remaining is only $10
# enforcer.record_charge("cust_123", amount=20.0)

# Check budget status
status = enforcer.check_limit("cust_123")
print(f"Used: ${status.used}, Limit: ${status.limit}, Remaining: ${status.remaining}")
print(f"Enforced: {status.enforced}")

# View charge history
history = enforcer.get_history("cust_123")
for charge in history:
    print(f"  ${charge.amount} — {charge.description} ({charge.provider})")
```

---

## Shared: kit-core

`kit-core` is auto-installed with any kit package. It provides:

| Module | What it does |
|--------|-------------|
| `kit_core.redis_client` | Async Redis client with connection pooling and singleton pattern |
| `kit_core.config` | Pydantic-based settings loaded from `KIT_*` env vars |
| `kit_core.logger` | Structured logging via structlog (JSON in production, console in dev) |
| `kit_core.exceptions` | Exception hierarchy shared across all packages |

```python
from kit_core import RedisClient, KitConfig, get_logger

# Config from environment
config = KitConfig()  # reads KIT_REDIS_URL, KIT_LOG_LEVEL, etc.

# Structured logging
logger = get_logger("my-service")
logger.info("order_created", order_id="ord_123", customer="cust_456")

# Redis singleton
redis = RedisClient.get_instance(config.redis_url)
```

---

## Example App

A fully working FastAPI app that demonstrates all three packages is included at `example-app/main.py`.

### Running the example

```bash
cd Kit-API-Optimization

# Install dependencies
pip install fastapi uvicorn fakeredis redis pydantic pydantic-settings structlog httpx

# Start the server
PYTHONPATH=kit-core:kit-api:kit-media:kit-pay:example-app \
  python -m uvicorn main:app --reload --port 8000
```

Then open **http://localhost:8000/docs** for the interactive Swagger UI where you can test every endpoint.

### Available demo endpoints

| Group | Endpoint | Method | Description |
|-------|----------|--------|-------------|
| **Rate Limiter** | `/api/rate-limit/test` | GET | Hit 10+ times to see rate limiting |
| | `/api/rate-limit/remaining` | GET | Check remaining quota |
| | `/api/rate-limit/reset` | POST | Reset counter |
| **Circuit Breaker** | `/api/circuit/status` | GET | View circuit state |
| | `/api/circuit/call` | POST | Simulate success/failure calls |
| | `/api/circuit/reset` | POST | Force-reset circuit |
| **Retry Engine** | `/api/retry/demo` | POST | Simulate retries with backoff |
| **Idempotency** | `/api/idempotent/order` | POST | Create order with `Idempotency-Key` header |
| **Cost Tracker** | `/api/cost/record` | POST | Record API call cost |
| | `/api/cost/usage` | GET | View usage by provider |
| | `/api/cost/budget` | POST | Set spending budget |
| **Media Transform** | `/media/transform` | POST | Build CDN transform URL |
| | `/media/validate` | GET | Validate MIME type |
| **CDN Router** | `/media/cdn/resolve` | GET | Route to best CDN by region |
| | `/media/cdn/all` | GET | Get all CDN URLs |
| **Webhooks** | `/pay/webhook/{provider}` | POST | Receive and process webhook |
| | `/pay/webhook/events` | GET | List processed events |
| **Subscriptions** | `/pay/subscription/create` | POST | Create subscription |
| | `/pay/subscription/{id}` | GET | Get subscription details |
| | `/pay/subscription/{id}/transition` | POST | Change subscription state |
| **Budget** | `/pay/budget/set-limit` | POST | Set customer spending limit |
| | `/pay/budget/charge` | POST | Record charge (blocks if over budget) |
| | `/pay/budget/status` | GET | Check budget status |
| | `/pay/budget/history` | GET | View charge history |

---

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio fakeredis

# Run all tests (82 tests)
PYTHONPATH=kit-core:kit-api:kit-media:kit-pay \
  pytest kit-core/tests/ kit-api/tests/ kit-media/tests/ kit-pay/tests/ -v \
  --override-ini="asyncio_mode=auto"
```

---

## Configuration

All packages share configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KIT_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `KIT_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `KIT_ENVIRONMENT` | `development` | `development` or `production` (affects log format) |
| `KIT_DEBUG` | `false` | Enable debug mode |

---

## Project Structure

```
Kit-API-Optimization/
├── pyproject.toml                 # Workspace root
├── .github/workflows/             # CI per package
│   ├── ci-core.yml
│   ├── ci-api.yml
│   ├── ci-media.yml
│   └── ci-pay.yml
├── docs/
├── example-app/
│   ├── main.py                    # FastAPI demo app
│   └── requirements.txt
├── kit-core/                      # Shared utilities
│   ├── kit_core/
│   │   ├── redis_client.py
│   │   ├── config.py
│   │   ├── logger.py
│   │   └── exceptions.py
│   └── tests/
├── kit-api/                       # API optimization
│   ├── kit_api/
│   │   ├── rate_limiter.py
│   │   ├── circuit_breaker.py
│   │   ├── retry_engine.py
│   │   ├── idempotency.py
│   │   ├── cost_tracker.py
│   │   ├── middleware/ (django.py, fastapi.py)
│   │   └── adapters/ (redis_adapter.py, celery_adapter.py)
│   └── tests/
├── kit-media/                     # Media handling
│   ├── kit_media/
│   │   ├── presigned_url.py
│   │   ├── chunked_upload.py
│   │   ├── cdn_router.py
│   │   ├── processor.py
│   │   ├── caption_job.py
│   │   └── adapters/ (s3, r2, gcs)
│   └── tests/
└── kit-pay/                       # Payment processing
    ├── kit_pay/
    │   ├── idempotency_key.py
    │   ├── webhook_receiver.py
    │   ├── event_processor.py
    │   ├── plan_state.py
    │   ├── grace_handler.py
    │   ├── budget_enforcer.py
    │   └── adapters/ (stripe, paddle)
    └── tests/
```

## Author

**Moniruzzaman Shawon**
- Email: m.zaman.djp@gmail.com
- GitHub: [@Moniruzzaman-Shawon](https://github.com/Moniruzzaman-Shawon)

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Moniruzzaman Shawon
