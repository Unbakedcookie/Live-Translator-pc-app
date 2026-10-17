"""Streaming downmix + resample to 16 kHz mono float32 (T042; spec §5.3).

Windowed-sinc (Blackman) low-pass at 0.45 x 16 kHz removes everything ASR can't use and
anything that would alias, then linear interpolation picks the 16 kHz sample positions. The
filter history and the fractional read position carry across chunks, so feeding audio in any
chunk sizes gives the same output as feeding it all at once. Handles any input rate
(48 kHz, 44.1 kHz, ...), numpy only.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

TARGET_RATE = 16_000
CUTOFF_FRACTION = 0.45  # of the target rate: 7.2 kHz
TAPS = 101

Float = NDArray[np.float32]


def lowpass_fir(cutoff_hz: float, rate: int, taps: int = TAPS) -> NDArray[np.float64]:
    if taps % 2 == 0:
        raise ValueError("use an odd number of taps")
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff_hz / rate * n) * np.blackman(taps)
    return h / h.sum()


def to_mono(frames: NDArray[np.floating]) -> Float:
    if frames.ndim == 1:
        return frames.astype(np.float32, copy=False)
    return frames.mean(axis=1).astype(np.float32)


class StreamResampler:
    def __init__(self, in_rate: int, out_rate: int = TARGET_RATE, taps: int = TAPS) -> None:
        if in_rate <= 0 or out_rate <= 0:
            raise ValueError("rates must be positive")
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._step = in_rate / out_rate
        self._h = lowpass_fir(CUTOFF_FRACTION * out_rate, in_rate, taps)
        self._history = np.zeros(taps - 1, dtype=np.float64)
        self._pos = 0.0  # next output position, in filtered-input samples of the current chunk
        self._prev = 0.0  # last filtered sample of the previous chunk (index -1)

    def process(self, frames: NDArray[np.floating]) -> Float:
        mono = to_mono(frames).astype(np.float64)
        if mono.size == 0:
            return np.zeros(0, dtype=np.float32)
        x = np.concatenate([self._history, mono])
        y = np.convolve(x, self._h, mode="valid")  # one filtered sample per input sample
        self._history = x[-(len(self._h) - 1) :]
        last = len(y) - 1
        if self._pos > last:
            self._pos -= len(y)
            self._prev = float(y[-1])
            return np.zeros(0, dtype=np.float32)
        count = int(np.floor((last - self._pos) / self._step)) + 1
        positions = self._pos + self._step * np.arange(count)
        z = np.concatenate([[self._prev], y])  # z[i + 1] == y[i]
        out = np.interp(positions + 1.0, np.arange(len(z)), z)
        self._pos = positions[-1] + self._step - len(y)
        self._prev = float(y[-1])
        return out.astype(np.float32)
