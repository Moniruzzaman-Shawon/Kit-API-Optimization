"""Tests for kit_data.pagination.KeysetPaginator."""

from __future__ import annotations

import pytest
from kit_data.pagination import KeysetPaginator


def _fetch_for(data):
    """A fake keyset fetch over a pre-sorted list of integers."""
    def fetch(after, limit):
        start = 0
        if after is not None:
            start = next((i for i, v in enumerate(data) if v > after), len(data))
        return data[start : start + limit]
    return fetch


def _paginator(data, page_size=2):
    return KeysetPaginator(_fetch_for(data), key=lambda r: r, page_size=page_size)


def test_single_page_when_fewer_than_page_size():
    page = _paginator([1, 2], page_size=5).page()
    assert page.items == [1, 2]
    assert page.has_more is False
    assert page.next_cursor is None


def test_multiple_pages_with_cursor():
    p = _paginator([1, 2, 3, 4, 5], page_size=2)
    first = p.page()
    assert first.items == [1, 2]
    assert first.has_more is True
    assert first.next_cursor == 2

    second = p.page(after=first.next_cursor)
    assert second.items == [3, 4]
    assert second.has_more is True

    third = p.page(after=second.next_cursor)
    assert third.items == [5]
    assert third.has_more is False
    assert third.next_cursor is None


def test_iter_pages_covers_everything():
    pages = list(_paginator([1, 2, 3, 4, 5], page_size=2).iter_pages())
    assert [pg.items for pg in pages] == [[1, 2], [3, 4], [5]]
    assert pages[-1].has_more is False


def test_iter_items_yields_all_in_order():
    assert list(_paginator(list(range(7)), page_size=3).iter_items()) == list(range(7))


def test_empty_dataset():
    page = _paginator([], page_size=3).page()
    assert page.items == []
    assert page.has_more is False


def test_invalid_page_size():
    with pytest.raises(ValueError, match="page_size"):
        KeysetPaginator(_fetch_for([]), key=lambda r: r, page_size=0)
