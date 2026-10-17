"""Discord-to-audio lag calibration (T101; spec §5.13 step 1; D-025).

Discord's SPEAKING_START arrives over local IPC, while the same voice reaches our loopback
capture through Discord's audio pipeline, so the two clocks disagree by a roughly constant
lag. Each SPEAKING_START is paired with the nearest VAD onset on the Others stream within
`MAX_PAIR_S`; the lag is the median of (VAD onset - Discord start) over the first `SAMPLES`
pairs. The median ignores the odd mismatched pair (someone else's voice, a missed onset).
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

SAMPLES = 10
MIN_PAIRS = 3
MAX_PAIR_S = 2.0


def pair_onsets(
    discord_starts: Sequence[float], vad_onsets: Sequence[float], max_gap: float = MAX_PAIR_S
) -> list[float]:
    """(VAD onset - Discord start) for each Discord start that has a VAD onset nearby."""
    lags: list[float] = []
    for start in discord_starts:
        nearby = [onset for onset in vad_onsets if abs(onset - start) <= max_gap]
        if nearby:
            nearest = min(nearby, key=lambda onset: abs(onset - start))
            lags.append(nearest - start)
    return lags


def calibrate_lag(
    discord_starts: Sequence[float], vad_onsets: Sequence[float], samples: int = SAMPLES
) -> float | None:
    """Median lag over the first `samples` pairs, or None with fewer than MIN_PAIRS."""
    lags = pair_onsets(discord_starts, vad_onsets)[:samples]
    if len(lags) < MIN_PAIRS:
        return None
    return statistics.median(lags)
