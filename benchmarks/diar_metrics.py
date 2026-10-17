"""T035 — speaker-diarization metrics (Tier A: checked against hand-computed toy cases).

Segments are (start s, end s, label). Hypothesis labels are arbitrary ("0", "1", ...), so
they are mapped one-to-one onto reference speakers by the mapping with the largest total
overlap (brute force: at most a handful of speakers).

DER = (missed speech + false alarm + speaker confusion) / reference speech, evaluated on a
10 ms grid. A collar around every reference boundary is ignored (standard 0.25 s), because
where exactly a turn starts is fuzzy even for humans.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

Segment = tuple[float, float, str]
STEP = 0.01


@dataclass(frozen=True)
class DerResult:
    der: float
    miss: float
    false_alarm: float
    confusion: float
    reference_s: float
    mapping: dict[str, str]  # hypothesis label -> reference label


def _labels_at(segments: Sequence[Segment], frames: int) -> list[str | None]:
    grid: list[str | None] = [None] * frames
    for start, end, label in segments:
        for i in range(max(round(start / STEP), 0), min(round(end / STEP), frames)):
            if grid[i] is None:
                grid[i] = label
    return grid


def best_mapping(ref: Sequence[Segment], hyp: Sequence[Segment]) -> dict[str, str]:
    """Hypothesis label -> reference label maximising total overlap (one-to-one)."""
    ref_labels = sorted({s[2] for s in ref})
    hyp_labels = sorted({s[2] for s in hyp})
    overlap: dict[tuple[str, str], float] = {}
    for h_start, h_end, h in hyp:
        for r_start, r_end, r in ref:
            shared = min(h_end, r_end) - max(h_start, r_start)
            if shared > 0:
                overlap[(h, r)] = overlap.get((h, r), 0.0) + shared
    best: dict[str, str] = {}
    best_total = -1.0
    slots = ref_labels + [""] * max(len(hyp_labels) - len(ref_labels), 0)
    for perm in itertools.permutations(slots, len(hyp_labels)):
        total = sum(overlap.get((h, r), 0.0) for h, r in zip(hyp_labels, perm, strict=True))
        if total > best_total:
            best_total = total
            best = {h: r for h, r in zip(hyp_labels, perm, strict=True) if r}
    return best


def der(ref: Sequence[Segment], hyp: Sequence[Segment], collar: float = 0.25) -> DerResult:
    end = max([s[1] for s in ref] + [s[1] for s in hyp] + [0.0])
    frames = round(end / STEP) + 1
    ref_grid = _labels_at(ref, frames)
    hyp_grid = _labels_at(hyp, frames)
    ignored = [False] * frames
    for start, stop, _ in ref:
        for boundary in (start, stop):
            lo = max(round((boundary - collar) / STEP), 0)
            hi = min(round((boundary + collar) / STEP), frames)
            for i in range(lo, hi):
                ignored[i] = True
    mapping = best_mapping(ref, hyp)
    miss = fa = conf = total = 0
    for i in range(frames):
        if ignored[i]:
            continue
        r, h = ref_grid[i], hyp_grid[i]
        if r is not None:
            total += 1
            if h is None:
                miss += 1
            elif mapping.get(h) != r:
                conf += 1
        elif h is not None:
            fa += 1
    reference_s = total * STEP
    if total == 0:
        return DerResult(0.0, 0.0, 0.0, 0.0, 0.0, mapping)
    return DerResult(
        (miss + fa + conf) / total, miss / total, fa / total, conf / total, reference_s, mapping
    )


def turn_accuracy(
    ref: Sequence[Segment], turn_labels: Sequence[str | None]
) -> tuple[float, dict[str, str]]:
    """Share of reference turns given the right speaker (after the best one-to-one mapping).
    `turn_labels[i]` is the system's label for reference turn i (None = no label)."""
    pseudo_hyp = [
        (s[0], s[1], label) for s, label in zip(ref, turn_labels, strict=True) if label is not None
    ]
    mapping = best_mapping(ref, pseudo_hyp)
    right = sum(
        1
        for s, label in zip(ref, turn_labels, strict=True)
        if label is not None and mapping.get(label) == s[2]
    )
    return (right / len(ref) if ref else 0.0), mapping
