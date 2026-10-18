"""Speech pipeline wiring: devices → capture → ASR worker → store (T045; spec §5.3, §5.4, §6.4).

- "Me" captures the chosen microphone, "Others" the loopback of the chosen output device
  (saved by name; missing → Windows default + a status message).
- Muting a stream stops its capture (the mic isn't even opened while muted) and tells the
  worker to finish the current line and ignore the rest.
- Settings changes are pushed to the worker as an immutable AsrSettings snapshot.
- The echo filter (T046) runs here on the main thread: a final "Me" line that repeats an
  overlapping "Others" line is removed, whichever of the two finishes last.
All IO is injected so the wiring is tested without audio hardware.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from loguru import logger
from PySide6.QtCore import QObject

from livetranslator.core import actions as a
from livetranslator.core.chatlog import is_echo
from livetranslator.core.presets import effective
from livetranslator.core.state import AppConfig, Source, StatusLevel
from livetranslator.core.store import Store
from livetranslator.services.asr.base import SAMPLE_RATE
from livetranslator.services.asr.worker import AsrSettings, ASRWorker, LineAudio, LineAudioFn
from livetranslator.services.audio.capture import AudioCapture
from livetranslator.services.audio.devices import AudioDevice, DeviceList, match
from livetranslator.services.audio.level import SILENCE_DB, rms_dbfs
from livetranslator.services.audio.ring import RingBuffer
from livetranslator.services.speakers.worker import LabelJob, SpeakerSettings, SpeakerWorker

RING_SECONDS = 60.0  # spec §5.3
LEVEL_WINDOW_S = 0.1  # Settings meters read the last 100 ms (T072)
STREAM_NAMES = {Source.ME: "microphone", Source.OTHERS: "speakers"}


class CaptureHandle(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


CaptureFactory = Callable[
    [AudioDevice, RingBuffer, Callable[[StatusLevel, str], None]], CaptureHandle
]


def asr_settings(config: AppConfig) -> AsrSettings:
    enabled = {
        source
        for source, on in (
            (Source.ME, config.audio.mic_enabled),
            (Source.OTHERS, config.audio.others_enabled),
        )
        if on
    }
    return AsrSettings(
        update_interval_s=effective(config).asr_interval_s,  # game mode: ≥ 1.0 s (T092)
        my_language=config.my_language,
        vad=config.vad,
        enabled=frozenset(enabled),
        chinese_script=config.engines.chinese_script,
    )


def speaker_settings(config: AppConfig) -> SpeakerSettings:
    return SpeakerSettings(mode=config.speakers.mode, max_speakers=config.speakers.max_speakers)


def line_audio_to(speakers: SpeakerWorker) -> LineAudioFn:
    """The ASR worker's line-audio hook, feeding the speaker worker."""

    def hand_over(line: LineAudio) -> None:
        speakers.submit(
            LabelJob(
                line.utterance_id,
                line.audio,
                line.start,
                line.end,
                line.final,
                line.words,
                line.language,
            )
        )

    return hand_over


def _default_capture(
    device: AudioDevice, ring: RingBuffer, on_status: Callable[[StatusLevel, str], None]
) -> AudioCapture:
    return AudioCapture(device, ring, on_status)


class SpeechController(QObject):
    def __init__(
        self,
        store: Store,
        worker: ASRWorker,
        list_devices: Callable[[], DeviceList],
        capture_factory: CaptureFactory = _default_capture,
        speakers: SpeakerWorker | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self.worker = worker
        self.speakers = speakers
        self._list_devices = list_devices
        self._capture_factory = capture_factory
        self.captures: dict[Source, CaptureHandle] = {}
        self.devices: dict[Source, AudioDevice] = {}
        self._rings: dict[Source, RingBuffer] = {}
        self._applied: tuple[object, ...] | None = None
        store.config_changed.connect(self._on_config_changed)
        store.utterance_updated.connect(self._check_echo)
        store.session_cleared.connect(self._on_session_cleared)

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self.worker.configure(asr_settings(self._store.state.config))
        if self.speakers is not None:
            self.speakers.configure(speaker_settings(self._store.state.config))
            self.speakers.start()
        self._apply_audio()
        self.worker.start()

    def stop(self) -> None:
        for source in list(self.captures):
            self._stop_capture(source)
        self.worker.stop()
        if self.speakers is not None:
            self.speakers.stop()

    def available_devices(self) -> DeviceList:
        """The device lists for Settings → Audio (T072). May raise if Windows audio is down."""
        return self._list_devices()

    def level_db(self, source: Source) -> float | None:
        """Loudness of the last 100 ms of a running stream; None when it isn't capturing."""
        ring = self._rings.get(source)
        if ring is None or source not in self.captures:
            return None
        end = ring.total_written
        start = max(ring.oldest_available, end - int(LEVEL_WINDOW_S * SAMPLE_RATE))
        if end <= start:
            return SILENCE_DB
        return rms_dbfs(ring.read(start, end))

    def _on_session_cleared(self) -> None:
        if self.speakers is not None:
            self.speakers.reset()  # voices are never remembered across sessions (D-028)

    # ------------------------------------------------------------ config

    def _on_config_changed(self, section: str) -> None:
        if section in ("audio", "my_language", "performance", "vad", "engines", "all"):
            self.worker.configure(asr_settings(self._store.state.config))
        if section in ("audio", "all"):
            self._apply_audio()
        if section in ("speakers", "all") and self.speakers is not None:
            self.speakers.configure(speaker_settings(self._store.state.config))

    def _status(self, source: Source, level: StatusLevel, message: str) -> None:
        self._store.dispatch(a.SetStatus(f"audio.{source.value}", level, message))

    def _apply_audio(self) -> None:
        audio = self._store.state.config.audio
        wanted = (audio.mic_enabled, audio.others_enabled, audio.mic_device, audio.output_device)
        if wanted == self._applied:
            return
        self._applied = wanted
        try:
            devices = self._list_devices()
        except Exception as exc:  # PortAudio failed to start: no audio at all
            logger.error("audio device listing failed ({})", type(exc).__name__)
            for source in (Source.ME, Source.OTHERS):
                self._status(source, StatusLevel.ERROR, "Windows audio isn't available.")
            return
        plan = {
            Source.ME: (
                audio.mic_enabled,
                match(audio.mic_device, devices.inputs, devices.default_input),
                audio.mic_device,
            ),
            Source.OTHERS: (
                audio.others_enabled,
                match(audio.output_device, devices.loopbacks, devices.default_loopback),
                audio.output_device,
            ),
        }
        for source, (enabled, device, saved) in plan.items():
            current = self.devices.get(source)
            if not enabled or device is None or (current is not None and current != device):
                self._stop_capture(source)
            if not enabled:
                self._status(source, StatusLevel.OK, f"{STREAM_NAMES[source].capitalize()} muted.")
                continue
            if device is None:
                self._status(
                    source,
                    StatusLevel.WARNING,
                    f"No {STREAM_NAMES[source]} found. Check Windows sound settings.",
                )
                continue
            # Own key: the capture's "Listening to …" status must not hide this warning.
            fallback_key = f"audio.{source.value}.device"
            if saved is not None and device.ref != saved:
                self._store.dispatch(
                    a.SetStatus(
                        fallback_key,
                        StatusLevel.WARNING,
                        f"{saved.name} isn't connected, so the Windows default is used.",
                    )
                )
            else:
                self._store.dispatch(a.ClearStatus(fallback_key))
            if source not in self.captures:
                self._start_capture(source, device)

    def _start_capture(self, source: Source, device: AudioDevice) -> None:
        ring = self._rings.get(source)
        if ring is None:
            ring = RingBuffer(RING_SECONDS, SAMPLE_RATE)
            self._rings[source] = ring
            self.worker.add_stream(source, ring)
        capture = self._capture_factory(
            device, ring, lambda level, message: self._status(source, level, message)
        )
        capture.start()
        self.captures[source] = capture
        self.devices[source] = device

    def _stop_capture(self, source: Source) -> None:
        capture = self.captures.pop(source, None)
        self.devices.pop(source, None)
        if capture is not None:
            capture.stop()

    # ------------------------------------------------------------ echo filter (T046)

    def _check_echo(self, utterance_id: str) -> None:
        state = self._store.state
        changed = state.session.utterance(utterance_id)
        if changed is None or not changed.is_final:
            return
        recent = state.session.utterances[-50:]
        config = state.config.echo_filter
        if changed.source is Source.ME:
            candidates = [changed]
        elif changed.source is Source.OTHERS:
            candidates = [u for u in recent if u.source is Source.ME and u.is_final]
        else:
            return
        others = [u for u in recent if u.source is Source.OTHERS and u.is_final]
        for me in candidates:
            if is_echo(me, others, config):
                self._store.dispatch(a.RemoveUtterance(me.id))
