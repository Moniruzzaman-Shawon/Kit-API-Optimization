# kit-pay

Payment processing toolkit providing idempotency, webhook handling, event processing, subscription plan state management, grace periods, and budget enforcement.

## Installation

```bash
pip install kit-pay

# With Stripe support
pip install kit-pay[stripe]

# With Paddle support
pip install kit-pay[paddle]
```

## Quick start

```python
from redis import Redis
from kit_pay import (
    IdempotencyKeyManager,
    WebhookReceiver,
    PlanStateManager,
    PlanState,
    BudgetEnforcer,
)

redis = Redis()

# Idempotency
idem = IdempotencyKeyManager(redis)
key = idem.generate("charge", "cust_123", "order_456")
if idem.acquire_lock(key):
    # process payment ...
    idem.mark_completed(key, {"charge_id": "ch_xyz"})

# Webhooks
receiver = WebhookReceiver(redis)
receiver.register_handler("invoice.paid", handle_invoice_paid)
event = receiver.parse(raw_payload, provider="stripe")
result = receiver.process(event)

# Plan state
plans = PlanStateManager(redis)
plans.transition("sub_001", PlanState.ACTIVE)

# Budget enforcement
budget = BudgetEnforcer(redis)
budget.set_limit("cust_123", amount=500.0, period="monthly")
budget.record_charge("cust_123", 49.99, description="Pro plan")
status = budget.check_limit("cust_123")
```
