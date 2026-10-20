"""Voice activity detection and utterance segmentation (T043; spec §5.4; D-016).

- `SileroVad`: streaming wrapper around the Silero VAD v6 ONNX model that ships inside
  faster-whisper (MIT). One 512-sample frame (32 ms at 16 kHz) in, a speech probability out;
  the recurrent state and the 64-sample context carry over between frames.
- `Segmenter`: pure state machine turning per-frame (probability, energy) into utterance
  open/close events. Frame i covers samples [512 i, 512 (i + 1)).
  * open: first frame with prob >= threshold, moved back by a short pre-roll so onsets
    aren't clipped;
  * close: after `end_silence_ms` of frames below the release threshold (hysteresis:
    threshold - 0.15); the close frame is just after the last speech frame;
  * hard cut at `max_utterance_s`: close at the lowest-energy frame of the last 2 s and open
    a new utterance right there, so long monologues still flow out in pieces.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from livetranslator.core.state import VadConfig

SAMPLE_RATE = 16_000
FRAME = 512
FRAME_MS = FRAME * 1000 / SAMPLE_RATE  # 32 ms
CONTEXT = 64
PREROLL_FRAMES = 3  # ~96 ms kept before the first speech frame
CUT_SEARCH_S = 2.0
HYSTERESIS = 0.15


@dataclass(frozen=True)
class VadEvent:
    kind: Literal["open", "close"]
    frame: int
    reason: Literal["speech", "silence", "max_length", "flush"] = "speech"

    @property
    def sample(self) -> int:
        return self.frame * FRAME


def frames_for_ms(ms: float) -> int:
    return max(1, math.ceil(ms / FRAME_MS))


class Segmenter:
    def __init__(self, config: VadConfig | None = None) -> None:
        cfg = config or VadConfig()
        self._on = cfg.threshold
        self._off = max(cfg.threshold - HYSTERESIS, 0.01)
        self._end_silence = frames_for_ms(cfg.end_silence_ms)
        self._max_frames = frames_for_ms(cfg.max_utterance_s * 1000)
        self._cut_window = frames_for_ms(CUT_SEARCH_S * 1000)
        self._frame = 0  # index of the next frame to be pushed
        self._open_at: int | None = None
        self._last_speech = -1
        self._energy: deque[tuple[int, float]] = deque(maxlen=self._cut_window)

    @property
    def is_open(self) -> bool:
        return self._open_at is not None

    def push(self, prob: float, energy: float) -> list[VadEvent]:
        i = self._frame
        self._frame += 1
        self._energy.append((i, energy))
        events: list[VadEvent] = []
        if self._open_at is None:
            if prob >= self._on:
                self._open_at = max(0, i - PREROLL_FRAMES)
                self._last_speech = i
                events.append(VadEvent("open", self._open_at))
            return events
        if prob >= self._off:
            self._last_speech = i
        elif i - self._last_speech >= self._end_silence:
            events.append(VadEvent("close", self._last_speech + 1, "silence"))
            self._open_at = None
            return events
        if i + 1 - self._open_at >= self._max_frames:
            cut = min(self._energy, key=lambda item: item[1])[0]
            cut = max(cut, self._open_at + 1)
            events.append(VadEvent("close", cut, "max_length"))
            events.append(VadEvent("open", cut, "max_length"))
            self._open_at = cut
        return events

    def flush(self) -> list[VadEvent]:
        """Stream ended: close an open utterance at the last pushed frame."""
        if self._open_at is None:
            return []
        self._open_at = None
        return [VadEvent("close", self._frame, "flush")]


def frame_energy(frame: NDArray[np.float32]) -> float:
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))


def default_model_path() -> Path:
    # faster_whisper imports PyAV, which the app doesn't ship (D-027): the same stand-in the
    # speech engine uses (2026-10-19: the first build failed here, PyAV hid it in development).
    from livetranslator.services.asr.faster_whisper_engine import ensure_av_importable

    ensure_av_importable()
    import faster_whisper

    return Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"


class SileroVad:
    """Frame-by-frame Silero VAD v6 on CPU (about 0.1 ms per 32 ms frame)."""

    def __init__(self, model_path: Path | None = None) -> None:
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self._session: Any = onnxruntime.InferenceSession(
            str(model_path or default_model_path()),
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def __call__(self, frame: NDArray[np.float32]) -> float:
        if frame.shape != (FRAME,):
            raise ValueError(f"expected {FRAME} samples, got {frame.shape}")
        window = np.concatenate([self._context, frame])[None, :].astype(np.float32)
        out, self._h, self._c = self._session.run(
            None, {"input": window, "h": self._h, "c": self._c}
        )
        self._context = frame[-CONTEXT:].astype(np.float32)
        return float(np.asarray(out).reshape(-1)[0])
