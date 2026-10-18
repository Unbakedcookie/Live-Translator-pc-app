"""Loudness of a short audio slice, for the Settings → Audio meters (T072; spec §5.8)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

SILENCE_DB = -90.0  # floor: digital silence would be -inf
METER_FLOOR_DB = -60.0  # the meter's empty point; speech at a normal level sits around -30..-15


def rms_dbfs(samples: NDArray[np.float32]) -> float:
    """RMS level in dB relative to full scale (a ±1.0 square wave = 0 dB)."""
    if len(samples) == 0:
        return SILENCE_DB
    rms = math.sqrt(float(np.mean(np.square(samples, dtype=np.float64))))
    if rms <= 0.0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(rms))


def meter_fraction(db: float) -> float:
    """Map dBFS onto a 0..1 meter: METER_FLOOR_DB and below = empty, 0 dB = full."""
    return min(1.0, max(0.0, (db - METER_FLOOR_DB) / -METER_FLOOR_DB))
