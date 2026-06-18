"""In-memory batch loader (DataLoader) that eliminates N+1 query patterns."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Sequence
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

BatchFn = Callable[["list[K]"], "dict[K, V] | Sequence[V]"]


class BatchLoader(Generic[K, V]):
    """Coalesce many single-key loads into one batched fetch.

    Solves the N+1 problem: instead of one query per item, collect the keys and
    resolve them in a single ``batch_fn`` call, with an in-instance cache so a key
    is never fetched twice. Create one loader per request / unit of work.

    ``batch_fn`` receives the list of distinct, uncached keys and must return either
    a ``dict`` keyed by those keys, or a sequence aligned to the input order. Keys
    with no value resolve to ``None``.

    Example
    -------
    >>> loader = BatchLoader(lambda ids: {u.id: u for u in db.users(id__in=ids)})
    >>> users = loader.load_many([p.author_id for p in posts])   # one query, not N
    """

    def __init__(self, batch_fn: BatchFn[K, V], *, cache: bool = True) -> None:
        self._batch_fn = batch_fn
        self._cache_enabled = cache
        self._cache: dict[K, V | None] = {}

    def load(self, key: K) -> V | None:
        """Load a single key (deduplicated and cached with other loads)."""
        return self.load_many([key])[0]

    def load_many(self, keys: Iterable[K]) -> list[V | None]:
        """Load many keys in one batched fetch, preserving input order."""
        keys = list(keys)
        resolved: dict[K, V | None] = {}
        missing: list[K] = []
        for k in keys:
            if self._cache_enabled and k in self._cache:
                resolved[k] = self._cache[k]
            elif k not in missing:
                missing.append(k)

        if missing:
            fetched = self._normalize(missing, self._batch_fn(missing))
            for k in missing:
                value = fetched.get(k)
                resolved[k] = value
                if self._cache_enabled:
                    self._cache[k] = value

        return [resolved.get(k) for k in keys]

    @staticmethod
    def _normalize(keys: list[K], result: dict[K, V] | Sequence[V]) -> dict[K, V]:
        if isinstance(result, dict):
            return result
        values = list(result)
        if len(values) != len(keys):
            raise ValueError(
                f"batch_fn returned {len(values)} values for {len(keys)} keys; "
                "return a dict keyed by id, or a sequence aligned to the input order"
            )
        return dict(zip(keys, values, strict=True))

    def prime(self, key: K, value: V | None) -> BatchLoader[K, V]:
        """Seed the cache with an already-known value."""
        if self._cache_enabled:
            self._cache[key] = value
        return self

    def clear(self, key: K) -> BatchLoader[K, V]:
        """Drop a single key from the cache."""
        self._cache.pop(key, None)
        return self

    def clear_all(self) -> BatchLoader[K, V]:
        """Drop the entire cache."""
        self._cache.clear()
        return self
