# kit-core — Shared utilities

`kit-core` is installed automatically with any Kit package. It provides the Redis client,
configuration, structured logging, and the shared exception hierarchy used across `kit-api`,
`kit-media`, and `kit-pay`.

← Back to [docs index](index.md) · See also the [Usage Guide](guide.md)

## Modules

| Module | What it does |
|--------|-------------|
| `kit_core.redis_client` | Async Redis client with connection pooling and a per-URL singleton |
| `kit_core.config` | Pydantic settings loaded from `KIT_*` environment variables |
| `kit_core.logger` | Structured logging via structlog (JSON in production, console in dev) |
| `kit_core.exceptions` | Exception hierarchy shared across all packages |

## Quick reference

```python
from kit_core import RedisClient, KitConfig, get_logger

config = KitConfig()                       # reads KIT_REDIS_URL, KIT_LOG_LEVEL, ...
redis = RedisClient.get_instance(config.redis_url)   # singleton per URL

logger = get_logger("my-service")
logger.info("order_created", order_id="ord_123", customer="cust_456")
```

## Exceptions

`kit_core.exceptions` defines the domain errors raised by the other packages — for example
`RateLimitExceeded`, `CircuitOpen`, and `IdempotencyConflict`. Catch them where you call the
corresponding Kit component:

```python
from kit_core.exceptions import RateLimitExceeded, CircuitOpen
```

> Note: these names are intentionally **not** suffixed with `Error` (they're part of the public
> API), which is why ruff's `N818` rule is disabled in the root `pyproject.toml`.

## Configuration

See [`index.md`](index.md) for the full `KIT_*` environment-variable table and defaults.
