"""kit-data: Redis-backed data-access optimization (batching, caching, bulkheads)."""

from __future__ import annotations

from kit_data.batch_loader import BatchLoader
from kit_data.cache import Cache, cached
from kit_data.concurrency import ConcurrencyLimiter
from kit_data.counter import Counter
from kit_data.exceptions import ConcurrencyLimitExceeded, NoHealthyReplicas
from kit_data.pagination import KeysetPaginator, Page
from kit_data.replica_router import Replica, ReplicaRouter

__all__ = [
    "BatchLoader",
    "Cache",
    "cached",
    "ConcurrencyLimiter",
    "ConcurrencyLimitExceeded",
    "Replica",
    "ReplicaRouter",
    "NoHealthyReplicas",
    "KeysetPaginator",
    "Page",
    "Counter",
]
