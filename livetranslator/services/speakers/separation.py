"""Separate people talking over each other (optional, experimental; user request 2026-10-20).

When two people talk at once, the app hears one mix: Whisper writes mostly the louder voice
and the line gets one label. With this on, every finished "Others" line is first checked for
two-talker speech (pyannote segmentation-3.0, ONNX, MIT; D-043). Only a line with at least
FLAG_S of overlap is split into two voices (ConvTasNet trained on Libri2Mix, ONNX,
CC-BY-SA-4.0; D-042), each voice is recognised on its own, and the line becomes two lines,
each with its own speaker label and translation. The original line is shown first, so the
split costs no delay; it arrives a few seconds later (full-app soak: 3.5-10 s for 7-15 s
lines, with other work sharing the machine). Both models run on the processor.

The split is kept only when both voices give real, different text; otherwise the original
line stays as it was (separation can leave one track nearly silent, or leak the same voice
into both). Measured on FLEURS mixtures: both talkers understood in 72 % of overlapped lines
vs 0 % without; detector flagged 91 % of overlaps and 0 % of 320 one-talker clips
(benchmarks/results/separation.md).

Lines without overlap pass straight on to speaker labels after the check (~8 ms per second
of audio). Game mode turns this off (it competes with the game for the processor).
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from numpy.typing import NDArray
from rapidfuzz import fuzz

from livetranslator.core import actions as a
from livetranslator.core.state import Source, Utterance
from livetranslator.services.asr.chinese import ChineseScript, is_chinese, to_script
from livetranslator.services.asr.worker import LineAudio

Float = NDArray[np.float32]
Emit = Callable[[a.Action], None]
# (audio, the languages people speak: () = any) -> (text, language)
Transcribe = Callable[[Float, tuple[str, ...]], tuple[str, str | None]]

OVERLAP_ID = "overlap-pyannote-seg3"
SEPARATION_ID = "separation-convtasnet"
MODEL_IDS = (OVERLAP_ID, SEPARATION_ID)
OVERLAP_MODEL = Path("separation") / "overlap" / "model.onnx"
SEPARATION_MODEL = Path("separation") / "convtasnet" / "model.onnx"

SAMPLE_RATE = 16_000
WINDOW = 160_000  # the segmentation model's 10 s window
FRAME = 270  # its output step in samples
OVERLAP_CLASSES = (4, 5, 6)  # powerset classes with two speakers
FLAG_S = 0.5  # two-talker speech needed before a line is split (D-043)
MIN_LINE_S = 2.0  # shorter lines are too short to hold two real turns
MIN_WORDS = 2  # each voice needs this many words (MIN_CHARS for Chinese/Japanese/Korean)
MIN_CHARS = 3
SAME_TEXT = 80  # rapidfuzz token_set_ratio: both tracks heard the same voice
ONSET = 0.1  # share of a track's peak that counts as its voice starting
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def installed(models_dir: Path) -> bool:
    return (models_dir / OVERLAP_MODEL).is_file() and (models_dir / SEPARATION_MODEL).is_file()


def _session(path: Path) -> Any:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


class OverlapDetector:
    """Seconds of two-talker speech in a line (pyannote segmentation-3.0, 10 s windows)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._session: Any = None

    def overlap_seconds(self, audio: Float) -> float:
        if self._session is None:
            self._session = _session(self._path)
        total = 0
        for start in range(0, len(audio), WINDOW):
            chunk = audio[start : start + WINDOW]
            if len(chunk) < SAMPLE_RATE // 2:
                break
            x = np.zeros((1, 1, WINDOW), dtype=np.float32)
            x[0, 0, : len(chunk)] = chunk
            classes = self._session.run(None, {"x": x})[0][0].argmax(axis=-1)
            total += int(np.isin(classes[: len(chunk) // FRAME], OVERLAP_CLASSES).sum())
        return total * FRAME / SAMPLE_RATE


class Separator:
    """Two voices from one mix (ConvTasNet), each at the mix's loudness."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._session: Any = None

    def separate(self, audio: Float) -> list[Float]:
        if self._session is None:
            self._session = _session(self._path)
        tracks = self._session.run(None, {"mix": audio[None, None, :].astype(np.float32)})[0][0]
        level = float(np.sqrt(np.mean(np.square(audio))) + 1e-9)
        out: list[Float] = []
        for track in tracks:
            rms = float(np.sqrt(np.mean(np.square(track))) + 1e-9)
            out.append((track * (level / rms)).astype(np.float32))
        return out


def enough_text(text: str) -> bool:
    if _CJK.search(text):
        return len(_CJK.findall(text)) >= MIN_CHARS
    return len(text.split()) >= MIN_WORDS


def onset(track: Float) -> int:
    loud = np.flatnonzero(np.abs(track) >= ONSET * float(np.max(np.abs(track)) or 1.0))
    return int(loud[0]) if len(loud) else len(track)


@dataclass(frozen=True)
class SeparationSettings:
    enabled: bool = False
    chinese_script: ChineseScript = "simplified"
    others_languages: tuple[str, ...] = ()  # Settings "Others speak"; () = detect any


@dataclass(frozen=True)
class Voice:
    audio: Float
    text: str
    language: str | None


class SeparationWorker:
    """Sits between the speech worker and the speaker worker for finished Others lines."""

    def __init__(
        self,
        models_dir: Path,
        transcribe: Transcribe,
        emit: Emit,
        forward: Callable[[LineAudio], None],
        exists: Callable[[str], bool],
        detector: OverlapDetector | None = None,
        separator: Separator | None = None,
    ) -> None:
        self._models_dir = models_dir
        self._transcribe = transcribe
        self._emit = emit
        self._forward = forward
        self._exists = exists
        self._detector = detector or OverlapDetector(models_dir / OVERLAP_MODEL)
        self._separator = separator or Separator(models_dir / SEPARATION_MODEL)
        self._own_models = detector is None and separator is None
        self._settings = SeparationSettings()
        self._jobs: queue.Queue[LineAudio | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.splits = 0

    # ------------------------------------------------------------ any thread

    @property
    def enabled(self) -> bool:
        if not self._settings.enabled:
            return False
        return installed(self._models_dir) if self._own_models else True

    def configure(self, settings: SeparationSettings) -> None:
        self._settings = settings

    def submit(self, line: LineAudio) -> None:
        """The speech worker's line-audio hook: finished lines get checked first."""
        if line.final and self.enabled:
            self._jobs.put(line)
        else:
            self._forward(line)

    # ------------------------------------------------------------ worker thread

    def handle(self, line: LineAudio) -> None:
        if len(line.audio) < MIN_LINE_S * SAMPLE_RATE:
            self._forward(line)
            return
        started = time.perf_counter()
        overlap = self._detector.overlap_seconds(line.audio)
        if overlap < FLAG_S:
            self._forward(line)
            return
        checked = time.perf_counter()
        voices = self._voices(line.audio)
        if voices is None or not self._exists(line.utterance_id):
            self._forward(line)
            return
        first, second = voices
        self._emit(
            a.UpdateUtterance(
                line.utterance_id,
                {
                    "committed": first.text,
                    "tentative": "",
                    "language": first.language,
                    "speaker_id": "others",
                },
            )
        )
        second_id = f"{line.utterance_id}-v2"
        self._emit(
            a.AddUtterance(
                Utterance(
                    id=second_id,
                    source=Source.OTHERS,
                    speaker_id="others",
                    start=line.start,
                    end=line.end,
                    committed=second.text,
                    language=second.language,
                    is_final=True,
                )
            )
        )
        for uid, voice in ((line.utterance_id, first), (second_id, second)):
            self._forward(
                replace(
                    line, utterance_id=uid, audio=voice.audio, words=(), language=voice.language
                )
            )
        self.splits += 1
        logger.info(
            "split a {:.1f} s line ({:.1f} s overlapping): check {:.0f} ms, split + recognise "
            "{:.0f} ms",
            len(line.audio) / SAMPLE_RATE,
            overlap,
            (checked - started) * 1000,
            (time.perf_counter() - checked) * 1000,
        )

    def _voices(self, audio: Float) -> tuple[Voice, Voice] | None:
        """The two voices, earlier one first; None when the split doesn't look real."""
        voices: list[Voice] = []
        for track in self._separator.separate(audio):
            text, language = self._transcribe(track, self._settings.others_languages)
            text = text.strip()
            if is_chinese(language):
                text = to_script(text, self._settings.chinese_script)
            if not enough_text(text):
                return None
            voices.append(Voice(track, text, language))
        if len(voices) != 2 or fuzz.token_set_ratio(voices[0].text, voices[1].text) >= SAME_TEXT:
            return None
        voices.sort(key=lambda v: onset(v.audio))
        return voices[0], voices[1]

    def run_pending(self) -> int:
        """Tests: process the queued lines on this thread."""
        done = 0
        while True:
            try:
                line = self._jobs.get_nowait()
            except queue.Empty:
                return done
            if line is None:
                return done
            self._safe_handle(line)
            done += 1

    def _safe_handle(self, line: LineAudio) -> None:
        try:
            self.handle(line)
        except Exception as exc:  # a failed split must never lose the line's label
            logger.warning("separating a line failed ({})", type(exc).__name__)
            self._forward(line)

    def _run(self) -> None:
        while True:
            line = self._jobs.get()
            if line is None:
                return
            self._safe_handle(line)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("separation worker already started")
        self._thread = threading.Thread(target=self._run, name="separation", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._jobs.put(None)
            self._thread.join(timeout)
            self._thread = None
