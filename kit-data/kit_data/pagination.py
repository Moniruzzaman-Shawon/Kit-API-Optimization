"""Keyset (cursor) pagination — avoids slow OFFSET scans on large tables."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

Row = TypeVar("Row")


@dataclass(frozen=True, slots=True)
class Page(Generic[Row]):
    """One page of keyset-paginated results."""

    items: list[Row]
    next_cursor: Any | None
    has_more: bool


class KeysetPaginator(Generic[Row]):
    """Cursor pagination that seeks by the last-seen key instead of OFFSET.

    ``OFFSET`` pagination scans and discards rows, so it gets slower the deeper you
    page. Keyset pagination uses ``WHERE sort_key > :cursor ORDER BY sort_key LIMIT :n``,
    which stays fast at any depth.

    Provide ``fetch(after, limit)`` returning up to ``limit`` rows ordered by the keyset
    and starting after ``after`` (``None`` for the first page), and ``key(row)`` to
    extract a row's cursor value.
    """

    def __init__(
        self,
        fetch: Callable[[Any | None, int], Sequence[Row]],
        *,
        key: Callable[[Row], Any],
        page_size: int = 50,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be >= 1")
        self._fetch = fetch
        self._key = key
        self._page_size = page_size

    def page(self, after: Any | None = None) -> Page[Row]:
        """Fetch a single page starting after ``after``."""
        rows = list(self._fetch(after, self._page_size + 1))
        has_more = len(rows) > self._page_size
        items = rows[: self._page_size]
        next_cursor = self._key(items[-1]) if has_more and items else None
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    def iter_pages(self, after: Any | None = None) -> Iterator[Page[Row]]:
        """Yield pages until the result set is exhausted."""
        cursor = after
        while True:
            current = self.page(cursor)
            yield current
            if not current.has_more:
                return
            cursor = current.next_cursor

    def iter_items(self, after: Any | None = None) -> Iterator[Row]:
        """Yield every row across all pages, in keyset order."""
        for current in self.iter_pages(after):
            yield from current.items
