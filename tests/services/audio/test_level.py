"""T072 — loudness maths for the Settings meters (Tier A, hand-computed)."""

import math

import numpy as np
import pytest

from livetranslator.services.audio.level import SILENCE_DB, meter_fraction, rms_dbfs


def test_rms_dbfs_reference_signals():
    square = np.array([1.0, -1.0] * 800, dtype=np.float32)
    assert rms_dbfs(square) == pytest.approx(0.0)
    assert rms_dbfs(square * 0.1) == pytest.approx(-20.0, abs=1e-4)  # 20·log10(0.1)
    t = np.arange(16000) / 16000
    sine = np.sin(2 * math.pi * 440 * t).astype(np.float32)
    assert rms_dbfs(sine) == pytest.approx(-3.0103, abs=1e-3)  # rms = 1/√2
    assert rms_dbfs(np.zeros(1600, dtype=np.float32)) == SILENCE_DB
    assert rms_dbfs(np.zeros(0, dtype=np.float32)) == SILENCE_DB
    assert rms_dbfs(square * 1e-6) == SILENCE_DB  # -120 dB is clamped to the floor


def test_meter_fraction_maps_minus_60_to_0_db():
    assert meter_fraction(-60.0) == 0.0
    assert meter_fraction(-90.0) == 0.0
    assert meter_fraction(-30.0) == 0.5
    assert meter_fraction(-15.0) == 0.75
    assert meter_fraction(0.0) == 1.0
    assert meter_fraction(3.0) == 1.0
