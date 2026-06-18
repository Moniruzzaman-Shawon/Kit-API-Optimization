# kit-data — Data-access optimization

Tools for the data tier: eliminate N+1 queries, cache reads safely under load, cap concurrent
expensive work, and spread reads across database replicas. **ORM-agnostic** — you provide a plain
loader/fetch function (SQLAlchemy, Django ORM, raw SQL, an HTTP API) and `kit-data` adds the smarts
around it.

**Install:** `pip install shawonkit-data` &nbsp;(imported as `kit_data`)

← Back to [docs index](index.md) · Problem-oriented walkthrough in the [Usage Guide](guide.md) ·
Full reference in the [README](../README.md)

## Components

| Component | Module | Solves |
|-----------|--------|--------|
| `BatchLoader` | `kit_data.batch_loader` | **N+1 queries** — coalesce many loads into one batched fetch |
| `Cache` / `cached` | `kit_data.cache` | Repeated reads + **cache stampede** (single-flight) |
| `ConcurrencyLimiter` | `kit_data.concurrency` | **Bulkhead** — cap concurrent expensive operations |
| `ReplicaRouter` | `kit_data.replica_router` | Spread reads across DB **read-replicas** with failover |

## Which tool for which "lots of requests" problem

| Situation | Tool |
|-----------|------|
| Many concurrent loads of **different** keys (the N+1 burst) | `BatchLoader` (batching) |
| Many concurrent requests for the **same** key (hot key) | `Cache` (single-flight) |
| A burst of **expensive** operations exhausting a resource | `ConcurrencyLimiter` (bulkhead) |
| Read traffic that should fan out across replicas | `ReplicaRouter` |

## Minimal examples

```python
from kit_data import BatchLoader, Cache, ConcurrencyLimiter, Replica, ReplicaRouter

# N+1 -> one query
authors = BatchLoader(lambda ids: {u.id: u for u in db.users(id__in=ids)}).load_many(ids)

# cache-aside with stampede protection
Cache(redis).get_or_set("user:42", lambda: load_user(42), ttl=300)

# bulkhead
with ConcurrencyLimiter(redis, name="reports", max_concurrent=10).slot():
    build_report()

# read-replica routing with failover
ReplicaRouter([Replica("a", eng_a), Replica("b", eng_b)]).run(lambda e: e.execute(sql))
```

See the [README](../README.md) for full parameters and the `@cached` decorator.
