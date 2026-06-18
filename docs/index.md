# Kit Documentation

**New here? Start with the [Usage Guide & Use Cases](guide.md)** — what problems Kit solves,
with copy-paste examples for each package.

## Packages

- [kit-core](core.md) — Shared utilities
- [kit-api](api.md) — API optimization tools
- [kit-media](media.md) — Media handling
- [kit-pay](pay.md) — Payment processing
- [kit-data](data.md) — Data-access optimization (N+1, caching, bulkheads, replica routing)

## Architecture

Kit is a modular monorepo. Each package is independently installable via pip, with `kit-core` as the shared dependency.

```
kit-core (shared: redis, config, logging, exceptions)
  ├── kit-api (rate limiting, circuit breakers, retries)
  ├── kit-media (uploads, CDN, media processing)
  ├── kit-pay (payments, webhooks, subscriptions)
  └── kit-data (N+1 batching, caching, bulkheads, replica routing)
```

## Configuration

All packages read configuration from environment variables prefixed with `KIT_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `KIT_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `KIT_LOG_LEVEL` | `INFO` | Logging level |
| `KIT_ENVIRONMENT` | `development` | Environment name |
| `KIT_DEBUG` | `false` | Debug mode |
