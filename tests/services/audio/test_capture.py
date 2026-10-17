"""T042 — capture worker: data path and device-lost recovery (fake streams) + live smoke."""

import sys
import threading
import time

import numpy as np
import pytest

from livetranslator.core.state import StatusLevel
from livetranslator.services.audio.capture import AudioCapture
from livetranslator.services.audio.devices import WASAPI, AudioDevice
from livetranslator.services.audio.ring import RingBuffer

MIC = AudioDevice(32, "Headset Microphone (3- A50 Mic)", WASAPI, 2, 48000)


class FakeStream:
    def __init__(self) -> None:
        self.active = True
        self.closed = False

    def is_active(self) -> bool:
        return self.active

    def close(self) -> None:
        self.closed = True


def wait_for(predicate, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def test_bytes_become_16k_mono_in_ring():
    ring = RingBuffer(60, 16000)
    statuses: list[tuple[StatusLevel, str]] = []
    received: list[int] = []
    feeds: list = []
    streams: list[FakeStream] = []

    def opener(device, on_bytes):
        feeds.append(on_bytes)
        streams.append(FakeStream())
        return streams[-1]

    capture = AudioCapture(
        MIC,
        ring,
        lambda lvl, msg: statuses.append((lvl, msg)),
        lambda s: received.append(len(s)),
        opener,
    )
    capture.start()
    wait_for(lambda: feeds)
    stereo = np.zeros((48000, 2), dtype=np.float32)  # 1 s of 48 kHz stereo silence
    feeds[0](stereo.tobytes())
    capture.stop()
    assert abs(ring.total_written - 16000) <= 1
    assert sum(received) == ring.total_written
    assert statuses == [(StatusLevel.OK, "Listening to Headset Microphone (3- A50 Mic)")]
    assert streams[0].closed


def test_device_lost_reports_and_reconnects():
    ring = RingBuffer(60, 16000)
    statuses: list[tuple[StatusLevel, str]] = []
    attempts = {"n": 0}
    streams: list[FakeStream] = []
    lock = threading.Lock()

    def opener(device, on_bytes):
        with lock:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError("device unplugged")
            streams.append(FakeStream())
            return streams[-1]

    capture = AudioCapture(
        MIC, ring, lambda lvl, msg: statuses.append((lvl, msg)), opener=opener, retry_s=0.05
    )
    capture.start()
    wait_for(lambda: len(streams) == 1)
    streams[0].active = False  # stream dies mid-session (headset unplugged)
    wait_for(lambda: len(streams) == 2)
    capture.stop()
    name = "Headset Microphone (3- A50 Mic)"
    assert statuses[:4] == [
        (StatusLevel.WARNING, f"{name} isn't available. Reconnecting…"),
        (StatusLevel.OK, f"Listening to {name}"),
        (StatusLevel.WARNING, f"{name} stopped. Reconnecting…"),
        (StatusLevel.OK, f"Listening to {name}"),
    ]
    assert all(s.closed for s in streams)


@pytest.mark.skipif(sys.platform != "win32", reason="real WASAPI devices")
def test_live_default_mic_delivers_samples():
    """Smoke only: opens the default mic for ~1 s; audio is counted, never stored."""
    from livetranslator.services.audio.devices import list_devices

    devices = list_devices()
    assert devices.default_input is not None
    ring = RingBuffer(5, 16000)
    statuses: list[StatusLevel] = []
    capture = AudioCapture(devices.default_input, ring, lambda lvl, msg: statuses.append(lvl))
    capture.start()
    try:
        # Poll instead of a fixed sleep: opening the device can be slow under heavy CPU load.
        wait_for(lambda: ring.total_written > 8000, timeout=5.0)  # >= 0.5 s at 16 kHz
    finally:
        capture.stop()
    assert statuses and statuses[0] is StatusLevel.OK
