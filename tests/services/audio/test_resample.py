"""T042 — resampler and ring buffer (Tier A, hand-checked signals)."""

import numpy as np
import pytest

from livetranslator.services.audio.resample import StreamResampler, lowpass_fir, to_mono
from livetranslator.services.audio.ring import RingBuffer


def sine(freq: float, rate: int, seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def run_chunked(resampler: StreamResampler, signal: np.ndarray, sizes: list[int]) -> np.ndarray:
    out, i, k = [], 0, 0
    while i < len(signal):
        n = sizes[k % len(sizes)]
        out.append(resampler.process(signal[i : i + n]))
        i += n
        k += 1
    return np.concatenate(out)


def dominant_frequency(x: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.fft.rfftfreq(len(x), 1 / rate)[np.argmax(spectrum)])


@pytest.mark.parametrize("in_rate", [48_000, 44_100])
def test_1khz_sine_keeps_frequency_and_amplitude(in_rate):
    mono = sine(1000, in_rate, 2.0)
    stereo = np.stack([mono, mono], axis=1)
    out = run_chunked(StreamResampler(in_rate), stereo, [480, 1024, 333, 4096])
    # Length: 2 s at 16 kHz = 32000 samples (+-1 from the fractional phase).
    assert abs(len(out) - 32_000) <= 1
    steady = out[1600:-1600]  # skip the filter's start-up transient
    assert dominant_frequency(steady, 16_000) == pytest.approx(1000, rel=0.01)
    amplitude = float(np.sqrt(2) * np.sqrt(np.mean(steady.astype(np.float64) ** 2)))
    assert amplitude == pytest.approx(0.5, rel=0.01)


def test_chunking_gives_identical_output():
    signal = np.random.default_rng(7).standard_normal(48_000).astype(np.float32) * 0.1
    whole = StreamResampler(48_000).process(signal)
    pieces = run_chunked(StreamResampler(48_000), signal, [1, 7, 512, 3, 1000])
    assert len(pieces) == len(whole)
    assert np.allclose(pieces, whole, atol=1e-6)


def test_out_of_band_tone_is_removed():
    out = StreamResampler(48_000).process(sine(12_000, 48_000, 1.0))  # above 8 kHz Nyquist
    assert float(np.max(np.abs(out[400:]))) < 0.01  # >= 34 dB down instead of aliasing


def test_downmix_and_filter_basics():
    assert to_mono(np.array([[0.2, 0.4], [-1.0, 1.0]], dtype=np.float32)).tolist() == (
        pytest.approx([0.3, 0.0])
    )
    h = lowpass_fir(7200, 48_000)
    assert len(h) == 101 and h.sum() == pytest.approx(1.0)
    with pytest.raises(ValueError):
        lowpass_fir(7200, 48_000, taps=100)


def test_ring_buffer_wraps_and_reads_by_absolute_index():
    ring = RingBuffer(seconds=1.0, rate=5)  # capacity 5
    ring.write(np.arange(3, dtype=np.float32))  # 0 1 2
    ring.write(np.arange(3, 7, dtype=np.float32))  # 3 4 5 6 -> keeps 2..6
    assert ring.total_written == 7
    assert ring.oldest_available == 2
    assert ring.read(0).tolist() == [2, 3, 4, 5, 6]  # overwritten part skipped
    assert ring.read(4, 6).tolist() == [4, 5]
    assert ring.read(5).tolist() == [5, 6]
    assert ring.read(7).tolist() == []
    ring.write(np.arange(100, 112, dtype=np.float32))  # longer than capacity
    assert ring.read(0).tolist() == [107, 108, 109, 110, 111]
