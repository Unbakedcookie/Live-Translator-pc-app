"""Mic and speaker meters before the speech pipeline runs (setup wizard, T073).

The wizard asks which microphone and which speakers to use before any speech model is
downloaded, so the SpeechController (which needs the model) can't run yet. This opens just
the chosen devices with the same capture code and reports their loudness; nothing is kept.
"""

from __future__ import annotations

from collections.abc import Callable

from livetranslator.core.state import DeviceRef, Source
from livetranslator.services.asr.base import SAMPLE_RATE
from livetranslator.services.audio.capture import AudioCapture
from livetranslator.services.audio.devices import AudioDevice, DeviceList, list_devices, match
from livetranslator.services.audio.level import SILENCE_DB, rms_dbfs
from livetranslator.services.audio.ring import RingBuffer

WINDOW_S = 0.1  # the meters read the last 100 ms, like Settings → Audio
RING_S = 2.0

CaptureFactory = Callable[[AudioDevice, RingBuffer], AudioCapture]


def _capture(device: AudioDevice, ring: RingBuffer) -> AudioCapture:
    return AudioCapture(device, ring, lambda _level, _message: None)


class LevelProbe:
    def __init__(
        self,
        list_fn: Callable[[], DeviceList] = list_devices,
        make_capture: CaptureFactory = _capture,
    ) -> None:
        self._list = list_fn
        self._make = make_capture
        self._devices: DeviceList | None = None
        self._captures: dict[Source, tuple[AudioDevice, AudioCapture, RingBuffer]] = {}

    def devices(self) -> DeviceList:
        if self._devices is None:
            self._devices = self._list()
        return self._devices

    def use(self, source: Source, saved: DeviceRef | None) -> AudioDevice | None:
        """Listen to the device `saved` points at (None = the Windows default). Returns the
        device opened, or None when there isn't one."""
        devices = self.devices()
        if source is Source.ME:
            device = match(saved, devices.inputs, devices.default_input)
        else:
            device = match(saved, devices.loopbacks, devices.default_loopback)
        current = self._captures.get(source)
        if current is not None and current[0] == device:
            return device
        self._stop(source)
        if device is None:
            return None
        ring = RingBuffer(RING_S, SAMPLE_RATE)
        capture = self._make(device, ring)
        capture.start()
        self._captures[source] = (device, capture, ring)
        return device

    def level_db(self, source: Source) -> float | None:
        current = self._captures.get(source)
        if current is None:
            return None
        ring = current[2]
        end = ring.total_written
        start = max(ring.oldest_available, end - int(WINDOW_S * SAMPLE_RATE))
        return SILENCE_DB if end <= start else rms_dbfs(ring.read(start, end))

    def _stop(self, source: Source) -> None:
        current = self._captures.pop(source, None)
        if current is not None:
            current[1].stop()

    def stop(self) -> None:
        for source in list(self._captures):
            self._stop(source)
