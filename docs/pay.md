# kit-pay — Payment processing

Tools for safe payments, webhooks, and subscription lifecycles — idempotent, deduplicated, and
backed by Redis.

**Install:** `pip install shawonkit-pay` (provider adapters: `shawonkit-pay[stripe]`, `shawonkit-pay[paddle]`)

← Back to [docs index](index.md) · Problem-oriented walkthrough in the [Usage Guide](guide.md) ·
Full reference in the [README](../README.md)

## Components

| Component | Solves |
|-----------|--------|
| `IdempotencyKeyManager` | Deterministic keys + distributed locks to prevent duplicate charges |
| `WebhookReceiver` | HMAC verification, provider normalization, dedup by event ID |
| `EventProcessor` | Async event queue with retry and dead-letter handling |
| `PlanStateManager` | Subscription lifecycle as a validated finite state machine |
| `GraceHandler` | Payment grace periods with reminders and state transitions |
| `BudgetEnforcer` | Per-customer spend limits that block over-budget charges |

All are importable from the top-level package, e.g. `from kit_pay import WebhookReceiver`.

## Minimal example

```python
from kit_pay import WebhookReceiver

receiver = WebhookReceiver(redis)
if not receiver.verify(raw_body, signature, secret="whsec_..."):
    raise Unauthorized()
event = receiver.parse(raw_body, provider="stripe")
receiver.register_handler("invoice.paid", activate_subscription)
result = receiver.process(event)            # SUCCESS / SKIPPED (duplicate) / FAILED
```

## Provider adapters

`from kit_pay.adapters.stripe_adapter import StripeAdapter` ·
`from kit_pay.adapters.paddle_adapter import PaddleAdapter`. Install the matching extra so the
provider SDK is present.

See the [README](../README.md#package-3-kit-pay--payment-processing) for the full subscription
state machine, grace/budget APIs, and FastAPI webhook example.
