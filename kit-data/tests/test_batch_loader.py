"""Tests for kit_data.batch_loader.BatchLoader."""

from __future__ import annotations

import pytest
from kit_data.batch_loader import BatchLoader


def test_load_many_calls_batch_fn_once():
    calls = []

    def batch_fn(ids):
        calls.append(list(ids))
        return {i: i * 10 for i in ids}

    loader = BatchLoader(batch_fn)
    result = loader.load_many([1, 2, 3])

    assert result == [10, 20, 30]
    assert calls == [[1, 2, 3]]  # exactly one batched call


def test_deduplicates_keys_in_one_batch():
    calls = []

    def batch_fn(ids):
        calls.append(list(ids))
        return {i: i for i in ids}

    loader = BatchLoader(batch_fn)
    result = loader.load_many([1, 1, 2, 1, 2])

    assert result == [1, 1, 2, 1, 2]
    assert calls == [[1, 2]]  # each distinct key fetched once


def test_caches_across_calls():
    calls = []

    def batch_fn(ids):
        calls.append(list(ids))
        return {i: i for i in ids}

    loader = BatchLoader(batch_fn)
    loader.load(1)
    loader.load(1)
    loader.load_many([1, 2])

    assert calls == [[1], [2]]  # 1 fetched once, 2 fetched once


def test_missing_keys_resolve_to_none():
    loader = BatchLoader(lambda ids: {1: "a"})
    assert loader.load_many([1, 2]) == ["a", None]


def test_accepts_aligned_sequence_result():
    loader = BatchLoader(lambda ids: [i * 2 for i in ids])
    assert loader.load_many([5, 6]) == [10, 12]


def test_sequence_length_mismatch_raises():
    loader = BatchLoader(lambda ids: [1])  # wrong length
    with pytest.raises(ValueError, match="aligned"):
        loader.load_many([1, 2])


def test_prime_and_clear():
    calls = []

    def batch_fn(ids):
        calls.append(list(ids))
        return {i: i for i in ids}

    loader = BatchLoader(batch_fn)
    loader.prime(1, 99)
    assert loader.load(1) == 99
    assert calls == []  # primed value served without a fetch

    loader.clear(1)
    loader.load(1)
    assert calls == [[1]]  # refetched after clear


def test_cache_disabled_refetches():
    calls = []

    def batch_fn(ids):
        calls.append(list(ids))
        return {i: i for i in ids}

    loader = BatchLoader(batch_fn, cache=False)
    loader.load(1)
    loader.load(1)
    assert calls == [[1], [1]]
