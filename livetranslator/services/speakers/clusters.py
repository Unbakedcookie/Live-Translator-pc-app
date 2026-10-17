"""Online voice clusters: "Speaker 1", "Speaker 2", ... (T102; spec §5.13 Source A).

Each line's voice fingerprint (a unit-length embedding) joins the known speaker it is most
similar to, if the cosine similarity reaches `threshold`; otherwise it starts a new speaker,
up to `max_speakers` (then it joins the closest one). A speaker's fingerprint is the running
duration-weighted sum of its lines. Benchmark (T035): similarity 0.5-0.6 labelled 93 % of
turns right with TitaNet. Fingerprints live in memory only and are never saved (D-028).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float32]

DEFAULT_THRESHOLD = 0.55


@dataclass(frozen=True)
class Assignment:
    cluster: str | None  # "0", "1", ...; None = no match and not allowed to create one
    similarity: float | None  # to the matched speaker; None for a newly created speaker
    created: bool = False


def unit(vector: Vector) -> Vector:
    norm = float(np.linalg.norm(vector))
    return (vector / norm).astype(np.float32) if norm > 0 else vector.astype(np.float32)


class VoiceClusters:
    """Thread-safe speaker memory for one session."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, max_speakers: int = 6) -> None:
        self.threshold = threshold
        self.max_speakers = max_speakers
        self._sums: list[Vector] = []
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        return len(self._sums)

    def _best(self, vector: Vector) -> tuple[int, float] | None:
        if not self._sums:
            return None
        sims = [float(np.dot(vector, unit(s))) for s in self._sums]
        best = int(np.argmax(sims))
        return best, sims[best]

    def peek(self, vector: Vector) -> Assignment:
        """Who this probably is, without learning from it (partial lines)."""
        with self._lock:
            best = self._best(unit(vector))
        if best is not None and best[1] >= self.threshold:
            return Assignment(str(best[0]), best[1])
        return Assignment(None, best[1] if best else None)

    def assign(self, vector: Vector, weight: float = 1.0) -> Assignment:
        """Label a finished line and learn from it."""
        vector = unit(vector)
        with self._lock:
            best = self._best(vector)
            if best is not None and (
                best[1] >= self.threshold or len(self._sums) >= self.max_speakers
            ):
                index, similarity = best
                self._sums[index] = (self._sums[index] + weight * vector).astype(np.float32)
                return Assignment(str(index), similarity)
            self._sums.append((weight * vector).astype(np.float32))
            return Assignment(str(len(self._sums) - 1), None, created=True)

    def reset(self) -> None:
        with self._lock:
            self._sums = []
