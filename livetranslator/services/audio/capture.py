"""Audio capture worker: WASAPI stream -> 16 kHz mono -> ring buffer (T042; spec §5.3, §6.4).

One worker per stream ("Me" = mic, "Others" = loopback). A missing or unplugged device is
reported as a plain-language status and retried every `retry_s` seconds; capture resumes by
itself when the device comes back. Note: WASAPI loopback delivers no packets while nothing
is playing, so silence on "Others" simply means no data, not an error.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np
from loguru import logger

from livetranslator.core.state import StatusLevel
from livetranslator.services.audio.devices import AudioDevice
from livetranslator.services.audio.resample import Float, StreamResampler
from livetranslator.services.audio.ring import RingBuffer

RETRY_S = 2.0
POLL_S = 0.2
FRAMES_PER_BUFFER = 1024

StatusFn = Callable[[StatusLevel, str], None]
AudioFn = Callable[[Float], None]
RawCallback = Callable[[bytes], None]


class StreamHandle(Protocol):
    def is_active(self) -> bool: ...

    def close(self) -> None: ...


Opener = Callable[[AudioDevice, RawCallback], StreamHandle]


class _PyAudioStream:
    """A PyAudioWPatch float32 input stream in callback mode."""

    def __init__(self, device: AudioDevice, on_bytes: RawCallback) -> None:
        import pyaudiowpatch as pa

        self._pa: Any = pa.PyAudio()

        def callback(
            in_data: bytes | None, frames: int, info: Any, status: int
        ) -> tuple[None, int]:
            if in_data:
                on_bytes(in_data)
            return None, pa.paContinue

        try:
            self._stream: Any = self._pa.open(
                format=pa.paFloat32,
                channels=device.channels,
                rate=device.sample_rate,
                input=True,
                input_device_index=device.index,
                frames_per_buffer=FRAMES_PER_BUFFER,
                stream_callback=callback,
            )
        except Exception:
            self._pa.terminate()
            raise

    def is_active(self) -> bool:
        try:
            return bool(self._stream.is_active())
        except OSError:
            return False

    def close(self) -> None:
        try:
            self._stream.stop_stream()
            self._stream.close()
        finally:
            self._pa.terminate()


def open_pyaudio(device: AudioDevice, on_bytes: RawCallback) -> StreamHandle:
    return _PyAudioStream(device, on_bytes)


class AudioCapture:
    def __init__(
        self,
        device: AudioDevice,
        ring: RingBuffer,
        on_status: StatusFn,
        on_audio: AudioFn | None = None,
        opener: Opener = open_pyaudio,
        retry_s: float = RETRY_S,
    ) -> None:
        self.device = device
        self._ring = ring
        self._on_status = on_status
        self._on_audio = on_audio
        self._opener = opener
        self._retry_s = retry_s
        self._resampler = StreamResampler(device.sample_rate)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _on_bytes(self, data: bytes) -> None:
        frames = np.frombuffer(data, dtype=np.float32).reshape(-1, self.device.channels)
        samples = self._resampler.process(frames)
        if samples.size:
            self._ring.write(samples)
            if self._on_audio is not None:
                self._on_audio(samples)

    def _run(self) -> None:
        name = self.device.ref.name
        while not self._stop.is_set():
            try:
                stream = self._opener(self.device, self._on_bytes)
            except Exception as exc:  # device missing, busy, or format refused
                logger.warning("capture open failed for a device ({})", type(exc).__name__)
                self._on_status(StatusLevel.WARNING, f"{name} isn't available. Reconnecting…")
                self._stop.wait(self._retry_s)
                continue
            self._on_status(StatusLevel.OK, f"Listening to {name}")
            try:
                while not self._stop.wait(POLL_S):
                    if not stream.is_active():
                        self._on_status(StatusLevel.WARNING, f"{name} stopped. Reconnecting…")
                        break
            finally:
                stream.close()
            if not self._stop.is_set():
                self._resampler = StreamResampler(self.device.sample_rate)
                self._stop.wait(self._retry_s)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("capture already started")
        self._thread = threading.Thread(
            target=self._run, name=f"capture-{self.device.index}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
