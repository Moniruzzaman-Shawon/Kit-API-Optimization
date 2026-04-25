"""
Bastion API — API Optimization Platform

Run:
    cd example-app
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Then open:
    http://localhost:8000/documentation  — Custom Bastion API docs
    http://localhost:8000/docs           — Swagger UI
    http://localhost:8000/redoc          — ReDoc
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import os
import pathlib

import fakeredis
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Bootstrap a fake Redis so the app runs without a real Redis server.
# In production, replace with: redis.Redis(host="localhost", port=6379, ...)
# ---------------------------------------------------------------------------
_raw_redis = fakeredis.FakeRedis(decode_responses=True)


class _RedisWrapper:
    """Thin wrapper so kit-api components can access .client as expected."""
    def __init__(self, redis):
        self.client = redis


_redis = _RedisWrapper(_raw_redis)

# kit-pay and kit-media components use raw Redis directly
_pay_redis = _raw_redis

# ── kit-core ──────────────────────────────────────────────────────────────────
from kit_core.exceptions import (
    CircuitOpen,
    IdempotencyConflict,
    RateLimitExceeded,
)
from kit_pay.budget_enforcer import PaymentError

# ── kit-api ───────────────────────────────────────────────────────────────────
from kit_api.rate_limiter import RateLimiter
from kit_api.circuit_breaker import CircuitBreaker, State
from kit_api.retry_engine import RetryEngine
from kit_api.idempotency import IdempotencyStore, CachedResponse
from kit_api.cost_tracker import CostTracker, Period

# ── kit-pay ───────────────────────────────────────────────────────────────────
from kit_pay.webhook_receiver import WebhookReceiver, ProcessStatus
from kit_pay.plan_state import PlanState, PlanStateManager, Subscription
from kit_pay.budget_enforcer import BudgetEnforcer

# ── kit-media ─────────────────────────────────────────────────────────────────
from kit_media.processor import MediaProcessor, TransformSpec, FitMode
from kit_media.cdn_router import CDNRouter, CDNEndpoint

# ---------------------------------------------------------------------------
# Instantiate kit components with our Redis instance
# ---------------------------------------------------------------------------
# Rate limiter: use a simple counter-based approach since fakeredis
# doesn't support Lua scripting. In production with real Redis, use
# the full RateLimiter class which uses atomic Lua scripts.


class SimpleRateLimiter:
    """Simplified rate limiter using basic Redis commands (no Lua)."""

    def __init__(self, redis, max_requests: int, window_seconds: int):
        self._redis = redis
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def acquire(self, key: str) -> bool:
        redis_key = f"demo:rl:{key}"
        now = time.time()
        window_start = now - self.window_seconds
        self._redis.zremrangebyscore(redis_key, 0, window_start)
        count = self._redis.zcard(redis_key)
        if count >= self.max_requests:
            raise RateLimitExceeded(f"Rate limit exceeded for {key}")
        self._redis.zadd(redis_key, {f"{now}-{uuid.uuid4().hex[:8]}": now})
        self._redis.expire(redis_key, self.window_seconds)
        return True

    def remaining(self, key: str) -> int:
        redis_key = f"demo:rl:{key}"
        now = time.time()
        self._redis.zremrangebyscore(redis_key, 0, now - self.window_seconds)
        count = self._redis.zcard(redis_key)
        return max(0, self.max_requests - count)

    def reset(self, key: str) -> None:
        self._redis.delete(f"demo:rl:{key}")


rate_limiter = SimpleRateLimiter(_raw_redis, max_requests=10, window_seconds=60)
circuit_breaker = CircuitBreaker(_redis, name="external-api", failure_threshold=3, recovery_timeout=30)
retry_engine = RetryEngine(max_retries=3, base_delay=0.1, max_delay=2.0)
idempotency_store = IdempotencyStore(_redis)
cost_tracker = CostTracker(_redis)

webhook_receiver = WebhookReceiver(_pay_redis)
plan_manager = PlanStateManager(_pay_redis)
budget_enforcer = BudgetEnforcer(_pay_redis)

media_processor = MediaProcessor(transform_base_url="https://images.example.com/transform")
cdn_router = CDNRouter(endpoints=[
    CDNEndpoint(name="us-cdn", base_url="https://us.cdn.example.com", regions=["us", "ca"], weight=3),
    CDNEndpoint(name="eu-cdn", base_url="https://eu.cdn.example.com", regions=["eu", "uk"], weight=2),
    CDNEndpoint(name="ap-cdn", base_url="https://ap.cdn.example.com", regions=["ap", "jp"], weight=1),
])

# Register a sample webhook handler
handled_events: list[dict] = []


def on_invoice_paid(event):
    handled_events.append({"type": event.type, "id": event.id, "provider": event.provider})
    return "processed"


webhook_receiver.register_handler("invoice.paid", on_invoice_paid)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="Bastion API",
    description="Production-grade API optimization platform — rate limiting, "
                "media handling, and payment processing.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Custom Documentation Page ─────────────────────────────────────────────────
_STATIC_DIR = pathlib.Path(__file__).parent / "static"


@app.get("/documentation", response_class=HTMLResponse, include_in_schema=False)
def bastion_docs():
    """Serve the custom Bastion API documentation portal."""
    html_path = _STATIC_DIR / "docs.html"
    return HTMLResponse(content=html_path.read_text(), status_code=200)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  kit-api endpoints                                                       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


# ── Rate Limiter ──────────────────────────────────────────────────────────────

@app.get("/api/rate-limit/test", tags=["kit-api: Rate Limiter"])
def test_rate_limit(client_id: str = "user-1"):
    """Hit this endpoint repeatedly to see rate limiting in action.

    Allows 10 requests per 60 seconds per client_id.
    """
    try:
        rate_limiter.acquire(client_id)
    except RateLimitExceeded:
        remaining = rate_limiter.remaining(client_id)
        raise HTTPException(status_code=429, detail={
            "error": "Rate limit exceeded",
            "remaining": remaining,
            "window_seconds": 60,
        })

    remaining = rate_limiter.remaining(client_id)
    return {"status": "allowed", "remaining": remaining, "client_id": client_id}


@app.get("/api/rate-limit/remaining", tags=["kit-api: Rate Limiter"])
def check_remaining(client_id: str = "user-1"):
    """Check how many requests remain in the current window."""
    return {"client_id": client_id, "remaining": rate_limiter.remaining(client_id)}


@app.post("/api/rate-limit/reset", tags=["kit-api: Rate Limiter"])
def reset_rate_limit(client_id: str = "user-1"):
    """Reset the rate limit counter for a client."""
    rate_limiter.reset(client_id)
    return {"status": "reset", "client_id": client_id}


# ── Circuit Breaker ──────────────────────────────────────────────────────────

@app.get("/api/circuit/status", tags=["kit-api: Circuit Breaker"])
def circuit_status():
    """Get the current state of the circuit breaker."""
    state = circuit_breaker.state
    return {"name": "external-api", "state": state.value, "failure_threshold": 3, "recovery_timeout": 30}


class SimulateRequest(BaseModel):
    success: bool = True


@app.post("/api/circuit/call", tags=["kit-api: Circuit Breaker"])
def simulate_circuit_call(body: SimulateRequest):
    """Simulate a call through the circuit breaker.

    Send `{"success": false}` to simulate failures. After 3 failures,
    the circuit opens and blocks all requests.
    """
    try:
        circuit_breaker.allow_request()
    except CircuitOpen as exc:
        raise HTTPException(status_code=503, detail={
            "error": "Circuit is open",
            "message": str(exc),
            "state": circuit_breaker.state.value,
        })

    if body.success:
        circuit_breaker.record_success()
        return {"result": "success", "state": circuit_breaker.state.value}
    else:
        circuit_breaker.record_failure()
        return {"result": "failure recorded", "state": circuit_breaker.state.value}


@app.post("/api/circuit/reset", tags=["kit-api: Circuit Breaker"])
def reset_circuit():
    """Force-reset the circuit breaker to CLOSED."""
    circuit_breaker.reset()
    return {"status": "reset", "state": "closed"}


# ── Retry Engine ──────────────────────────────────────────────────────────────

_retry_call_count = 0


@app.post("/api/retry/demo", tags=["kit-api: Retry Engine"])
def retry_demo(fail_times: int = 2):
    """Demonstrate retry with exponential backoff.

    The internal function fails `fail_times` before succeeding.
    Max retries is 3, so fail_times <= 3 will succeed.
    """
    global _retry_call_count
    _retry_call_count = 0

    def unreliable():
        global _retry_call_count
        _retry_call_count += 1
        if _retry_call_count <= fail_times:
            raise ConnectionError(f"Attempt {_retry_call_count} failed")
        return f"Succeeded on attempt {_retry_call_count}"

    try:
        result = retry_engine.execute(unreliable)
        return {"result": result, "attempts": _retry_call_count}
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail={
            "error": "All retries exhausted",
            "attempts": _retry_call_count,
            "last_error": str(exc),
        })


# ── Idempotency ──────────────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    item: str
    quantity: int = 1
    price: float = 9.99


@app.post("/api/idempotent/order", tags=["kit-api: Idempotency"])
def create_order_idempotent(
    body: CreateOrderRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    """Create an order with idempotency protection.

    Send the same `Idempotency-Key` header twice — the second call
    returns the cached response instead of creating a duplicate.
    """
    # Check cache
    cached = idempotency_store.check(idempotency_key)
    if cached is not None:
        return {"source": "cache", "order": cached.body}

    # Acquire lock
    try:
        idempotency_store.acquire_lock(idempotency_key)
    except IdempotencyConflict:
        raise HTTPException(status_code=409, detail="Request already in progress")

    # Process order
    order = {
        "order_id": uuid.uuid4().hex[:12],
        "item": body.item,
        "quantity": body.quantity,
        "total": round(body.quantity * body.price, 2),
        "created_at": time.time(),
    }

    # Cache response
    idempotency_store.store(
        idempotency_key,
        CachedResponse(status_code=200, body=order, headers={}),
        ttl=3600,
    )

    return {"source": "new", "order": order}


# ── Cost Tracker ─────────────────────────────────────────────────────────────

class RecordCostRequest(BaseModel):
    provider: str = "openai"
    endpoint: str = "chat/completions"
    cost: float = 0.03
    tokens: int | None = 1500


@app.post("/api/cost/record", tags=["kit-api: Cost Tracker"])
def record_cost(body: RecordCostRequest):
    """Record an API call cost."""
    cost_tracker.record(body.provider, body.endpoint, body.cost, body.tokens)
    return {"status": "recorded", "provider": body.provider, "cost": body.cost}


@app.get("/api/cost/usage", tags=["kit-api: Cost Tracker"])
def get_usage(provider: str = "openai", period: str = "daily"):
    """Get usage for a provider in the current period."""
    p = Period(period)
    usage = cost_tracker.get_usage(provider, p)
    budget = cost_tracker.check_budget(provider, p)
    return {
        "provider": provider,
        "period": period,
        "total_cost": usage,
        "budget_limit": budget.limit,
        "budget_remaining": budget.remaining,
        "budget_percentage": budget.percentage,
    }


class SetBudgetRequest(BaseModel):
    provider: str = "openai"
    limit: float = 100.0
    period: str = "daily"


@app.post("/api/cost/budget", tags=["kit-api: Cost Tracker"])
def set_budget(body: SetBudgetRequest):
    """Set a spending budget for a provider."""
    cost_tracker.set_budget(body.provider, body.limit, Period(body.period))
    return {"status": "budget set", "provider": body.provider, "limit": body.limit}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  kit-media endpoints                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TransformRequest(BaseModel):
    source_url: str = "https://cdn.example.com/photos/hero.jpg"
    width: int | None = 800
    height: int | None = 600
    format: str | None = "webp"
    quality: int | None = 80
    fit: str = "cover"


@app.post("/media/transform", tags=["kit-media: Processor"])
def transform_image(body: TransformRequest):
    """Build a CDN transform URL for an image.

    Returns the optimized URL with resize/format parameters.
    """
    spec = TransformSpec(
        width=body.width,
        height=body.height,
        format=body.format,
        quality=body.quality,
        fit=FitMode(body.fit),
    )
    url = media_processor.build_transform_url(body.source_url, spec)
    return {"original": body.source_url, "transformed_url": url, "spec": spec.to_params()}


@app.get("/media/validate", tags=["kit-media: Processor"])
def validate_media_type(content_type: str = "image/jpeg"):
    """Check if a MIME type is allowed for upload."""
    valid = MediaProcessor.validate_media_type(content_type)
    return {"content_type": content_type, "allowed": valid}


@app.get("/media/cdn/resolve", tags=["kit-media: CDN Router"])
def resolve_cdn(key: str = "images/hero.jpg", region: str | None = None):
    """Resolve the best CDN URL for an asset based on region."""
    url = cdn_router.resolve(key, region=region)
    return {"key": key, "region": region, "cdn_url": url}


@app.get("/media/cdn/all", tags=["kit-media: CDN Router"])
def resolve_all_cdns(key: str = "images/hero.jpg"):
    """Get URLs from all CDN endpoints for an asset."""
    urls = cdn_router.resolve_all(key)
    return {"key": key, "urls": urls}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  kit-pay endpoints                                                       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# ── Webhook Receiver ─────────────────────────────────────────────────────────

WEBHOOK_SECRET = "whsec_demo_secret_123"


@app.post("/pay/webhook/{provider}", tags=["kit-pay: Webhooks"])
async def receive_webhook(provider: str, request: Request):
    """Receive and process a payment webhook.

    **How to test with Postman:**

    1. Set the URL to `POST /pay/webhook/stripe`
    2. Set header `X-Webhook-Signature` to the HMAC-SHA256 of the body
       using secret `whsec_demo_secret_123`
    3. Send a JSON body like:
    ```json
    {"id": "evt_123", "type": "invoice.paid", "created": 1700000000, "data": {"amount": 5000}}
    ```

    Or use `/pay/webhook/test` to skip signature verification.
    """
    body = await request.body()

    # Skip signature check for the test endpoint
    if provider != "test":
        signature = request.headers.get("x-webhook-signature", "")
        if not webhook_receiver.verify(body, signature, WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = webhook_receiver.parse(body, provider=provider if provider != "test" else "stripe")
    result = webhook_receiver.process(event)

    return {
        "event_id": result.event_id,
        "status": result.status.value,
        "handler_results": result.handler_results,
        "error": result.error,
    }


@app.get("/pay/webhook/events", tags=["kit-pay: Webhooks"])
def list_handled_events():
    """List all webhook events that have been processed."""
    return {"events": handled_events}


# ── Subscription / Plan State ────────────────────────────────────────────────

class CreateSubscriptionRequest(BaseModel):
    subscription_id: str = "sub_001"
    customer_id: str = "cust_123"
    plan_id: str = "plan_pro"


@app.post("/pay/subscription/create", tags=["kit-pay: Subscriptions"])
def create_subscription(body: CreateSubscriptionRequest):
    """Create a new subscription (starts in TRIAL state)."""
    sub = Subscription(
        id=body.subscription_id,
        customer_id=body.customer_id,
        plan_id=body.plan_id,
        state=PlanState.TRIAL,
        current_period_end=time.time() + 30 * 86400,
    )
    plan_manager.create(sub)
    return {"subscription": _sub_to_dict(sub)}


@app.get("/pay/subscription/{subscription_id}", tags=["kit-pay: Subscriptions"])
def get_subscription(subscription_id: str):
    """Get subscription details and current state."""
    try:
        sub = plan_manager.get(subscription_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {
        "subscription": _sub_to_dict(sub),
        "is_active": plan_manager.is_active(subscription_id),
    }


class TransitionRequest(BaseModel):
    new_state: str = "active"


@app.post("/pay/subscription/{subscription_id}/transition", tags=["kit-pay: Subscriptions"])
def transition_subscription(subscription_id: str, body: TransitionRequest):
    """Transition a subscription to a new state.

    Valid states: `trial`, `active`, `past_due`, `grace`, `cancelled`, `expired`

    The state machine enforces valid transitions (e.g., trial -> active is OK,
    trial -> past_due is NOT).
    """
    try:
        new_state = PlanState(body.new_state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.new_state}")

    try:
        sub = plan_manager.transition(subscription_id, new_state)
    except KeyError:
        raise HTTPException(status_code=404, detail="Subscription not found")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "subscription": _sub_to_dict(sub),
        "is_active": plan_manager.is_active(subscription_id),
    }


def _sub_to_dict(sub: Subscription) -> dict:
    return {
        "id": sub.id,
        "customer_id": sub.customer_id,
        "plan_id": sub.plan_id,
        "state": sub.state.value,
        "current_period_end": sub.current_period_end,
        "grace_until": sub.grace_until,
    }


# ── Budget Enforcer ──────────────────────────────────────────────────────────

class SetLimitRequest(BaseModel):
    customer_id: str = "cust_123"
    amount: float = 100.0
    period: str = "monthly"


@app.post("/pay/budget/set-limit", tags=["kit-pay: Budget"])
def set_spending_limit(body: SetLimitRequest):
    """Set a spending limit for a customer."""
    budget_enforcer.set_limit(body.customer_id, body.amount, body.period)
    return {"status": "limit set", "customer_id": body.customer_id, "limit": body.amount}


class ChargeRequest(BaseModel):
    customer_id: str = "cust_123"
    amount: float = 25.0
    description: str = "API usage"
    provider: str = "stripe"


@app.post("/pay/budget/charge", tags=["kit-pay: Budget"])
def record_charge(body: ChargeRequest):
    """Record a charge against a customer's budget.

    Returns 402 if the charge would exceed the budget limit.
    """
    try:
        record = budget_enforcer.record_charge(
            body.customer_id, body.amount, body.description, body.provider
        )
    except PaymentError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    status = budget_enforcer.check_limit(body.customer_id)
    return {
        "charge": {"amount": record.amount, "description": record.description},
        "budget": {
            "used": status.used,
            "limit": status.limit,
            "remaining": status.remaining,
            "enforced": status.enforced,
        },
    }


@app.get("/pay/budget/status", tags=["kit-pay: Budget"])
def check_budget(customer_id: str = "cust_123"):
    """Check a customer's current budget status."""
    status = budget_enforcer.check_limit(customer_id)
    return {
        "customer_id": status.customer_id,
        "used": status.used,
        "limit": status.limit,
        "remaining": status.remaining,
        "period": status.period,
        "enforced": status.enforced,
    }


@app.get("/pay/budget/history", tags=["kit-pay: Budget"])
def charge_history(customer_id: str = "cust_123"):
    """Get charge history for a customer."""
    history = budget_enforcer.get_history(customer_id)
    return {
        "customer_id": customer_id,
        "charges": [
            {"amount": c.amount, "description": c.description, "provider": c.provider, "timestamp": c.timestamp}
            for c in history
        ],
    }


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Health & Info                                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

@app.get("/", tags=["Info"])
def root():
    """API overview — redirects to Bastion documentation."""
    return {
        "name": "Bastion API",
        "version": "0.1.0",
        "documentation": "/documentation",
        "swagger": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "api_optimization": {
                "rate_limiter": ["/api/rate-limit/test", "/api/rate-limit/remaining", "/api/rate-limit/reset"],
                "circuit_breaker": ["/api/circuit/status", "/api/circuit/call", "/api/circuit/reset"],
                "retry_engine": ["/api/retry/demo"],
                "idempotency": ["/api/idempotent/order"],
                "cost_tracker": ["/api/cost/record", "/api/cost/usage", "/api/cost/budget"],
            },
            "media_handling": {
                "processor": ["/media/transform", "/media/validate"],
                "cdn_router": ["/media/cdn/resolve", "/media/cdn/all"],
            },
            "payment_processing": {
                "webhooks": ["/pay/webhook/{provider}", "/pay/webhook/events"],
                "subscriptions": ["/pay/subscription/create", "/pay/subscription/{id}", "/pay/subscription/{id}/transition"],
                "budget": ["/pay/budget/set-limit", "/pay/budget/charge", "/pay/budget/status", "/pay/budget/history"],
            },
        },
    }
