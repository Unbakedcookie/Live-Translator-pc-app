"""Speaker change inside one line (T105; spec §5.13 "Utterance splitting").

Two people talking back-to-back with no pause end up in one VAD line. On a finished line of
at least LONG_LINE_S, 1.5 s windows (0.5 s hop) are matched against the speakers heard so
far (`VoiceClusters.peek`): each window gets a known speaker or None ("unclear"). Measured on
the T035 mixes, a single speaker's line never shows two different known speakers, while the
back-to-back lines did ("11111?????22", "???000"). So a change is declared when:
- a run of one known speaker is followed by a run of a *different* known speaker, or
- a run of >= NEW_RUN unclear windows (a new voice) is followed by a run of a known one
  (or the reverse),
with each run at least MIN_RUN windows long. The boundary estimate (between the two runs)
is then snapped to the nearest gap between recognised words, since people hand over
between words; that brings it within a word of the truth.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

WINDOW_S = 1.5
HOP_S = 0.5
LONG_LINE_S = 3.0
MIN_RUN = 2  # windows a known speaker must hold to count as a run
NEW_RUN = 3  # unclear windows needed to count as a (new) speaker run
MAX_SNAP_S = 0.8


@dataclass(frozen=True)
class Run:
    label: str | None
    first: int  # window index
    last: int


def runs(labels: Sequence[str | None]) -> list[Run]:
    found: list[Run] = []
    for i, label in enumerate(labels):
        if found and found[-1].label == label:
            found[-1] = Run(label, found[-1].first, i)
        else:
            found.append(Run(label, i, i))
    return found


def _long_enough(run: Run) -> bool:
    size = run.last - run.first + 1
    return size >= (NEW_RUN if run.label is None else MIN_RUN)


def window_center(index: int) -> float:
    return index * HOP_S + WINDOW_S / 2


def find_change(labels: Sequence[str | None]) -> float | None:
    """Estimated change time (s from line start), or None for a single speaker."""
    solid = [r for r in runs(labels) if _long_enough(r)]
    for left, right in itertools.pairwise(solid):
        if left.label == right.label:
            continue
        if left.label is None and right.label is None:
            continue
        return (window_center(left.last) + window_center(right.first)) / 2
    return None


def snap_to_words(estimate: float, words: Sequence[tuple[float, float]]) -> float:
    """The word gap (end of one word .. start of the next) nearest to `estimate`, if one is
    within MAX_SNAP_S; else the estimate. `words` are (start, end) in line time, in order."""
    best: tuple[float, float] | None = None
    for (_, end), (start, _) in itertools.pairwise(words):
        point = (end + start) / 2
        distance = abs(point - estimate)
        if distance <= MAX_SNAP_S and (best is None or distance < best[0]):
            best = (distance, point)
    return best[1] if best is not None else estimate


def window_starts(duration_s: float) -> list[float]:
    """Start times of the analysis windows covering a line of `duration_s`."""
    starts: list[float] = []
    t = 0.0
    while t + WINDOW_S <= duration_s + 1e-9:
        starts.append(round(t, 6))
        t += HOP_S
    return starts
