"""Speech-recognition engine contract (T016; spec §5.4). No engine library is imported here.

Audio is mono float32 PCM in [-1, 1] at `SAMPLE_RATE`. Timestamps are seconds from the start
of the buffer passed to `transcribe`. The streaming policy (LocalAgreement, T044) and the
worker (T045) are built on this contract, so any engine that satisfies it can be benchmarked
and swapped (faster-whisper, sherpa-onnx Parakeet, ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

SAMPLE_RATE = 16_000

Audio = NDArray[np.float32]


@dataclass(frozen=True)
class Word:
    text: str  # as the engine emits it, usually with its leading space
    start: float
    end: float
    probability: float | None = None


@dataclass(frozen=True)
class Segment:
    text: str
    start: float
    end: float
    words: tuple[Word, ...] = ()
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


@dataclass(frozen=True)
class Transcription:
    segments: tuple[Segment, ...]
    language: str | None = None  # detected (or forced) ISO 639-1 code
    language_probability: float | None = None

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def words(self) -> tuple[Word, ...]:
        return tuple(w for s in self.segments for w in s.words)


@runtime_checkable
class ASREngine(Protocol):
    name: str

    @property
    def is_loaded(self) -> bool: ...

    def load(self) -> None:
        """Load the model (slow; call from a worker thread, never the UI thread)."""
        ...

    def unload(self) -> None:
        """Free the model and its VRAM."""
        ...

    def transcribe(
        self,
        audio: Audio,
        *,
        language: str | None = None,
        prompt: str | None = None,
        final: bool = False,
    ) -> Transcription:
        """Transcribe `audio`. `language=None` asks the engine to detect it. `prompt` is
        preceding text that conditions decoding. `final=False` is a streaming partial (fast:
        greedy, no fallback); `final=True` is the utterance's last decode (accurate: beam
        search with temperature fallback; T045). Raises EngineNotLoaded before `load()`."""
        ...
