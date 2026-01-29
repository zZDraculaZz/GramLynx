"""Optional in-memory cache (LRU stub)."""
from __future__ import annotations

from collections import OrderedDict
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class LRUCache(Generic[T]):
    """Simple LRU cache."""

    def __init__(self, max_size: int = 128) -> None:
        self.max_size = max_size
        self._store: OrderedDict[str, T] = OrderedDict()

    def get(self, key: str) -> Optional[T]:
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def set(self, key: str, value: T) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)
