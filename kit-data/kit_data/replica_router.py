"""Client-side load balancing across database read-replicas."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from kit_data.exceptions import NoHealthyReplicas

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Replica:
    """A read-replica target. ``target`` is opaque — a DSN, engine, or session factory."""

    name: str
    target: Any
    weight: int = 1


class ReplicaRouter:
    """Spread read queries across healthy database read-replicas.

    A client-side load balancer for the data tier (the network load balancer in front
    of your *app* is infrastructure; this routes *reads* across DB replicas). It selects
    a replica by weighted random or round-robin, skips replicas marked unhealthy, and
    auto-recovers them after a cooldown. ``run`` adds automatic failover: if a replica
    errors, it is marked down and the next healthy one is tried.

    Health is tracked per-process — each app instance routes independently.
    """

    def __init__(
        self,
        replicas: list[Replica],
        *,
        strategy: str = "weighted",
        cooldown_seconds: float = 30.0,
        rng: random.Random | None = None,
    ) -> None:
        if strategy not in ("weighted", "round_robin"):
            raise ValueError(f"unknown strategy: {strategy!r}")
        if not replicas:
            raise ValueError("at least one replica is required")
        self._replicas = list(replicas)
        self._strategy = strategy
        self._cooldown = cooldown_seconds
        self._rng = rng or random.Random()
        self._down: dict[str, float] = {}
        self._rr = 0

    def _recover(self) -> None:
        now = time.monotonic()
        for name in [n for n, t in self._down.items() if now - t >= self._cooldown]:
            del self._down[name]

    def healthy(self) -> list[Replica]:
        """Return the currently healthy replicas (recovering any past their cooldown)."""
        self._recover()
        return [r for r in self._replicas if r.name not in self._down]

    def mark_down(self, name: str) -> None:
        """Mark a replica unhealthy; it recovers after the cooldown."""
        self._down[name] = time.monotonic()

    def mark_up(self, name: str) -> None:
        """Mark a replica healthy again immediately."""
        self._down.pop(name, None)

    def _select(self, pool: list[Replica]) -> Replica:
        if self._strategy == "round_robin":
            replica = pool[self._rr % len(pool)]
            self._rr += 1
            return replica
        total = sum(max(1, r.weight) for r in pool)
        pick = self._rng.uniform(0, total)
        upto = 0.0
        for replica in pool:
            upto += max(1, replica.weight)
            if pick <= upto:
                return replica
        return pool[-1]

    def route(self) -> Replica:
        """Pick one healthy replica, or raise ``NoHealthyReplicas``."""
        pool = self.healthy()
        if not pool:
            raise NoHealthyReplicas("no healthy read-replicas available")
        return self._select(pool)

    def run(self, fn: Callable[[Any], T]) -> T:
        """Run ``fn(replica.target)`` with automatic failover across replicas."""
        tried: set[str] = set()
        last_exc: Exception | None = None
        while True:
            pool = [r for r in self.healthy() if r.name not in tried]
            if not pool:
                break
            replica = self._select(pool)
            tried.add(replica.name)
            try:
                return fn(replica.target)
            except Exception as exc:  # failover: mark down and try the next replica
                last_exc = exc
                self.mark_down(replica.name)
        if last_exc is not None:
            raise last_exc
        raise NoHealthyReplicas("no healthy read-replicas available")
