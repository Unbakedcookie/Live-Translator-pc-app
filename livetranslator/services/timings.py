"""Duration recording for the performance readout (T091). Qt-free so the ASR and translation
workers can report into it from their own threads.

- `Timings.record("asr", seconds)` keeps the last `WINDOW` samples per kind.
- `percentile`: nearest-rank (p50 of 1..4 = 2, p95 of 1..20 = 19).
- `timed(timings, "mt")`: context manager timing a block (no-op without a recorder; a block
  that raises isn't recorded).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence

WINDOW = 50  # samples kept per kind (~ the last minute of conversation)


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


class Timings:
    def __init__(self, window: int = WINDOW) -> None:
        self._window = window
        self._samples: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def record(self, kind: str, seconds: float) -> None:
        """Any thread."""
        with self._lock:
            self._samples.setdefault(kind, deque(maxlen=self._window)).append(seconds)

    def snapshot(self, kind: str) -> list[float]:
        with self._lock:
            return list(self._samples.get(kind, ()))

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()


class timed:
    def __init__(
        self,
        timings: Timings | None,
        kind: str,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._timings = timings
        self._kind = kind
        self._clock = clock
        self._start = 0.0

    def __enter__(self) -> None:
        self._start = self._clock()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._timings is not None and exc_type is None:
            self._timings.record(self._kind, self._clock() - self._start)
