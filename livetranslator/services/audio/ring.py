"""Fixed-size audio ring buffer with absolute sample indices (T042; spec §5.3: 60 s max).

Writers append; readers ask for "everything since sample N" (the VAD/ASR keep their own
cursor), so several consumers can read without disturbing each other. Thread-safe.
"""

from __future__ import annotations

import threading

import numpy as np
from numpy.typing import NDArray

Float = NDArray[np.float32]


class RingBuffer:
    def __init__(self, seconds: float, rate: int) -> None:
        self.rate = rate
        self.capacity = int(seconds * rate)
        if self.capacity < 1:
            raise ValueError("ring buffer needs room for at least one sample")
        self._data = np.zeros(self.capacity, dtype=np.float32)
        self._written = 0  # total samples ever written (absolute index of the next sample)
        self._lock = threading.Lock()

    @property
    def total_written(self) -> int:
        with self._lock:
            return self._written

    @property
    def oldest_available(self) -> int:
        with self._lock:
            return max(0, self._written - self.capacity)

    def write(self, samples: Float) -> None:
        samples = samples[-self.capacity :]
        n = len(samples)
        if n == 0:
            return
        with self._lock:
            start = self._written % self.capacity
            first = min(n, self.capacity - start)
            self._data[start : start + first] = samples[:first]
            self._data[: n - first] = samples[first:]
            self._written += n

    def read(self, start: int, end: int | None = None) -> Float:
        """Samples [start, end) by absolute index; parts already overwritten are skipped."""
        with self._lock:
            end = self._written if end is None else min(end, self._written)
            start = max(start, self._written - self.capacity, 0)
            if start >= end:
                return np.zeros(0, dtype=np.float32)
            a, b = start % self.capacity, end % self.capacity
            if a < b or end - start == 0:
                return self._data[a:b].copy()
            return np.concatenate([self._data[a:], self._data[:b]])
