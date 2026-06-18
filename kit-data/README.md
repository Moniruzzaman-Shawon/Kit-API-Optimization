# shawonkit-data

Data-access optimization toolkit — eliminate N+1 queries, cache reads with stampede protection,
and cap concurrent expensive work. Built on top of `shawonkit-core`.

> Installed as `shawonkit-data`, imported as `kit_data`.

It is **ORM-agnostic**: you provide a plain fetch/loader function (SQLAlchemy, Django ORM, raw SQL,
an HTTP API — anything) and `kit_data` adds the batching, caching, and concurrency control around it.

## Installation

```bash
pip install shawonkit-data
```

## Usage

### BatchLoader — fix the N+1 problem

```python
from kit_data import BatchLoader

# batch_fn receives the distinct keys and returns a dict keyed by id
loader = BatchLoader(lambda ids: {u.id: u for u in db.users(id__in=ids)})

authors = loader.load_many([post.author_id for post in posts])  # ONE query, not N
one = loader.load(42)                                           # served from cache
```

### Cache — cache-aside with stampede protection

```python
from kit_data import Cache, cached

cache = Cache(redis, namespace="profiles", default_ttl=300)

# Only one worker recomputes a missing key at a time (single-flight).
profile = cache.get_or_set(f"user:{uid}", lambda: load_profile(uid), ttl=600)
cache.delete(f"user:{uid}")   # invalidate

@cached(ttl=60, redis=redis)
def expensive(query: str) -> dict:
    return run_report(query)
```

### ConcurrencyLimiter — bulkhead for bursts of expensive work

```python
from kit_data import ConcurrencyLimiter, ConcurrencyLimitExceeded

limiter = ConcurrencyLimiter(redis, name="report-gen", max_concurrent=10)
try:
    with limiter.slot():
        build_expensive_report()
except ConcurrencyLimitExceeded:
    return 503  # shed load instead of overwhelming the database
```

### ReplicaRouter — spread reads across DB replicas

```python
from kit_data import Replica, ReplicaRouter

router = ReplicaRouter([
    Replica("replica-a", engine_a, weight=2),
    Replica("replica-b", engine_b, weight=1),
], strategy="weighted")

# Automatic failover: a failing replica is marked down and the next is tried.
rows = router.run(lambda engine: engine.execute("SELECT ..."))
```

## License

MIT © Moniruzzaman Shawon
