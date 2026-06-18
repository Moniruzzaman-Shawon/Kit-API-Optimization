# kit-core

Shared foundation for the **Kit** toolkit — the Redis client, configuration, structured logging,
and the exception hierarchy used by [`kit-api`](https://pypi.org/project/kit-api/),
[`kit-media`](https://pypi.org/project/kit-media/), and
[`kit-pay`](https://pypi.org/project/kit-pay/).

It is installed automatically as a dependency of those packages; you rarely install it directly.

## Install

```bash
pip install kit-core
```

## What's inside

| Module | Purpose |
|--------|---------|
| `kit_core.redis_client` | Async Redis client with pooling and a per-URL singleton |
| `kit_core.config` | Pydantic settings from `KIT_*` environment variables |
| `kit_core.logger` | Structured logging via structlog |
| `kit_core.exceptions` | Shared exception hierarchy (`RateLimitExceeded`, `CircuitOpen`, …) |

## Quick start

```python
from kit_core import RedisClient, KitConfig, get_logger

config = KitConfig()                                  # reads KIT_REDIS_URL, KIT_LOG_LEVEL, …
redis = RedisClient.get_instance(config.redis_url)
log = get_logger("my-service")
log.info("started", redis_url=config.redis_url)
```

See the [project repository](https://github.com/Moniruzzaman-Shawon/Kit-API-Optimization) for the
full toolkit and documentation.

## License

MIT © Moniruzzaman Shawon
