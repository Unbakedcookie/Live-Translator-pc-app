"""Small thread-safe LRU cache for translations (T052; spec §5.5)."""

from __future__ import annotations

import threading
from collections import OrderedDict

DEFAULT_SIZE = 1000
CacheKey = tuple[str, str, str, str]  # (engine, src, tgt, text)


class TranslationCache:
    def __init__(self, maxsize: int = DEFAULT_SIZE) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self.maxsize = maxsize
        self._data: OrderedDict[CacheKey, str] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: CacheKey) -> str | None:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def put(self, key: CacheKey, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
