# kit-core

Shared foundation for the **Kit** toolkit — the Redis client, configuration, structured logging,
and the exception hierarchy used by [`shawonkit-api`](https://pypi.org/project/shawonkit-api/),
[`shawonkit-media`](https://pypi.org/project/shawonkit-media/), and
[`shawonkit-pay`](https://pypi.org/project/shawonkit-pay/).

It is installed automatically as a dependency of those packages; you rarely install it directly.

## Install

```bash
pip install shawonkit-core
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
