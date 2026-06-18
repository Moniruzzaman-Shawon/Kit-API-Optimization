"""Tests for kit_data.replica_router.ReplicaRouter."""

from __future__ import annotations

import random

import pytest
from kit_data.exceptions import NoHealthyReplicas
from kit_data.replica_router import Replica, ReplicaRouter


def _replicas():
    return [Replica("r1", "dsn-1"), Replica("r2", "dsn-2"), Replica("r3", "dsn-3")]


def test_round_robin_cycles():
    router = ReplicaRouter(_replicas(), strategy="round_robin")
    picked = [router.route().name for _ in range(6)]
    assert picked == ["r1", "r2", "r3", "r1", "r2", "r3"]


def test_weighted_only_returns_known_replicas():
    router = ReplicaRouter(_replicas(), rng=random.Random(0))
    for _ in range(20):
        assert router.route().name in {"r1", "r2", "r3"}


def test_mark_down_excludes_replica():
    router = ReplicaRouter(_replicas(), strategy="round_robin")
    router.mark_down("r2")
    assert {r.name for r in router.healthy()} == {"r1", "r3"}
    assert "r2" not in {router.route().name for _ in range(6)}


def test_route_raises_when_all_down():
    router = ReplicaRouter(_replicas())
    for r in ("r1", "r2", "r3"):
        router.mark_down(r)
    with pytest.raises(NoHealthyReplicas):
        router.route()


def test_cooldown_recovers_replica():
    router = ReplicaRouter(_replicas(), cooldown_seconds=0)
    router.mark_down("r1")
    # cooldown of 0 means it recovers on the next healthy() check
    assert "r1" in {r.name for r in router.healthy()}


def test_run_returns_result():
    router = ReplicaRouter(_replicas(), strategy="round_robin")
    assert router.run(lambda target: f"query@{target}") == "query@dsn-1"


def test_run_fails_over_and_marks_down():
    router = ReplicaRouter(_replicas(), strategy="round_robin")
    seen = []

    def query(target):
        seen.append(target)
        if target == "dsn-1":
            raise RuntimeError("replica down")
        return target

    result = router.run(query)
    assert result in {"dsn-2", "dsn-3"}   # failed over to a healthy replica
    assert "dsn-1" in seen                # the failing one was attempted
    assert "r1" not in {r.name for r in router.healthy()}  # and marked down


def test_run_raises_last_error_when_all_fail():
    router = ReplicaRouter(_replicas())

    def always_fail(target):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        router.run(always_fail)


def test_invalid_strategy_rejected():
    with pytest.raises(ValueError, match="strategy"):
        ReplicaRouter(_replicas(), strategy="nope")
