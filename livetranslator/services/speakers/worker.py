"""Speaker-label worker: voice fingerprints per "Others" line -> speaker ids (T102; §5.13).

The ASR worker hands over each Others line's audio twice: once while it is still a partial
(after ~1.5 s, for an early provisional label) and once when it is final. On its own thread
this worker computes the line's voice fingerprint and:
- partial: `peek`s at the known speakers (no learning); labels the line only on a match;
- final: `assign`s (learns), then fuses with Discord speaking data (none until T103) into
  "voice:<n>", "discord:<user>" or "others", and updates the line's `speaker_id`.
Fingerprints stay in memory and are dropped with the session (D-028).
"""

from __future__ import annotations

import queue
import threading
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from loguru import logger
from numpy.typing import NDArray

from livetranslator.core import actions as a
from livetranslator.core.state import Source, SpeakerMode, StatusLevel, Utterance
from livetranslator.services.speakers.base import SAMPLE_RATE, SpeakerEmbedder
from livetranslator.services.speakers.change import (
    LONG_LINE_S,
    WINDOW_S,
    find_change,
    snap_to_words,
    window_starts,
)
from livetranslator.services.speakers.clusters import DEFAULT_THRESHOLD, VoiceClusters
from livetranslator.services.speakers.fusion import (
    OTHERS,
    SpeakingInterval,
    add_vote,
    fuse,
)

Emit = Callable[[a.Action], None]
IntervalsFn = Callable[[float, float], Sequence[SpeakingInterval]]

MIN_EMBED_S = 0.5  # shorter audio gives meaningless fingerprints
MIN_PART_S = 1.0  # each side of a split must be a real turn
STATUS_KEY = "speakers"


def _join(words: Sequence[tuple[str, float, float]]) -> str:
    """Whisper words carry their own leading spaces (none for CJK)."""
    return "".join(text for text, _, _ in words).strip()


@dataclass(frozen=True)
class SpeakerSettings:
    mode: SpeakerMode = SpeakerMode.AUTO
    max_speakers: int = 6
    threshold: float = DEFAULT_THRESHOLD


@dataclass(frozen=True)
class LabelJob:
    utterance_id: str
    audio: NDArray[np.float32]
    start: float
    end: float
    final: bool
    words: tuple[tuple[str, float, float], ...] = ()  # (text, start, end) in line time
    language: str | None = None


class SpeakerWorker:
    def __init__(
        self,
        embedder: SpeakerEmbedder,
        emit: Emit,
        settings: SpeakerSettings | None = None,
        discord_intervals: IntervalsFn | None = None,
    ) -> None:
        self._embedder = embedder
        self._emit = emit
        self._settings = settings or SpeakerSettings()
        self._intervals = discord_intervals or (lambda start, end: ())
        self.clusters = VoiceClusters(self._settings.threshold, self._settings.max_speakers)
        self._votes: dict[str, Counter[str]] = {}
        self._jobs: queue.Queue[LabelJob | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._failed = False

    # ------------------------------------------------------------ any thread

    @property
    def enabled(self) -> bool:
        return self._settings.mode is not SpeakerMode.OFF and not self._failed

    def configure(self, settings: SpeakerSettings) -> None:
        self._settings = settings
        self.clusters.max_speakers = settings.max_speakers
        self.clusters.threshold = settings.threshold

    def submit(self, job: LabelJob) -> None:
        if self.enabled:
            self._jobs.put(job)

    def reset(self) -> None:
        """New session: forget every voice (fingerprints are never kept)."""
        self.clusters.reset()
        self._votes = {}

    # ------------------------------------------------------------ worker thread

    def _ensure_loaded(self) -> bool:
        if self._embedder.is_loaded:
            return True
        try:
            self._embedder.load()
        except Exception as exc:
            self._failed = True
            logger.error("speaker model failed to load ({})", type(exc).__name__)
            self._emit(
                a.SetStatus(
                    STATUS_KEY,
                    StatusLevel.WARNING,
                    "Speaker labels are off: the voice model couldn't be loaded.",
                )
            )
            return False
        return True

    def handle(self, job: LabelJob) -> None:
        """Process one job on the calling thread (tests, or the worker loop)."""
        settings = self._settings
        if settings.mode is SpeakerMode.OFF or len(job.audio) < MIN_EMBED_S * SAMPLE_RATE:
            return
        if not self._ensure_loaded():
            return
        use_voice = settings.mode in (SpeakerMode.AUTO, SpeakerMode.VOICE)
        use_discord = settings.mode in (SpeakerMode.AUTO, SpeakerMode.DISCORD)
        if job.final and use_voice and self._split_at_change(job, use_discord):
            return
        cluster: str | None = None
        confidence: float | None = None
        if use_voice:
            vector = self._embedder.embed(job.audio)
            seconds = len(job.audio) / SAMPLE_RATE
            if job.final:
                assignment = self.clusters.assign(vector, seconds)
            else:
                assignment = self.clusters.peek(vector)
                if assignment.cluster is None:
                    return  # nobody known yet: keep the neutral label until the line ends
            cluster, confidence = assignment.cluster, assignment.similarity
        intervals = self._intervals(job.start, job.end) if use_discord else ()
        result = fuse(job.start, job.end, cluster, confidence, intervals, self._votes)
        if job.final:
            self._votes = add_vote(self._votes, result.vote)
        if result.speaker_id == OTHERS and not job.final:
            return
        self._emit(a.UpdateUtterance(job.utterance_id, {"speaker_id": result.speaker_id}))

    def _label(self, audio: NDArray[np.float32], start: float, end: float, discord: bool) -> str:
        """Final label for one stretch of speech (learns its voice)."""
        assignment = self.clusters.assign(self._embedder.embed(audio), len(audio) / SAMPLE_RATE)
        intervals = self._intervals(start, end) if discord else ()
        result = fuse(start, end, assignment.cluster, assignment.similarity, intervals, self._votes)
        self._votes = add_vote(self._votes, result.vote)
        return result.speaker_id

    def _split_at_change(self, job: LabelJob, discord: bool) -> bool:
        """T105: two people back-to-back in one line -> two lines. True if it split."""
        duration = len(job.audio) / SAMPLE_RATE
        if duration < LONG_LINE_S or self.clusters.count == 0 or not job.words:
            return False
        window = int(WINDOW_S * SAMPLE_RATE)
        labels = [
            self.clusters.peek(
                self._embedder.embed(
                    job.audio[int(t * SAMPLE_RATE) : int(t * SAMPLE_RATE) + window]
                )
            ).cluster
            for t in window_starts(duration)
        ]
        estimate = find_change(labels)
        if estimate is None:
            return False
        cut = snap_to_words(estimate, [(s, e) for _, s, e in job.words])
        left = [w for w in job.words if (w[1] + w[2]) / 2 < cut]
        right = [w for w in job.words if (w[1] + w[2]) / 2 >= cut]
        if not left or not right or cut < MIN_PART_S or duration - cut < MIN_PART_S:
            return False
        sample = int(cut * SAMPLE_RATE)
        middle = job.start + cut
        left_id = self._label(job.audio[:sample], job.start, middle, discord)
        right_id = self._label(job.audio[sample:], middle, job.end, discord)
        self._emit(
            a.UpdateUtterance(
                job.utterance_id,
                {"committed": _join(left), "end": middle, "speaker_id": left_id},
            )
        )
        self._emit(
            a.AddUtterance(
                Utterance(
                    id=f"{job.utterance_id}-2",
                    source=Source.OTHERS,
                    speaker_id=right_id,
                    start=middle,
                    end=job.end,
                    committed=_join(right),
                    language=job.language,
                    is_final=True,
                )
            )
        )
        return True

    def run_pending(self) -> int:
        done = 0
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return done
            if job is None:
                return done
            self.handle(job)
            done += 1

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self.handle(job)
            except Exception as exc:  # one bad line must not stop speaker labels
                logger.warning("speaker label failed ({})", type(exc).__name__)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("speaker worker already started")
        self._thread = threading.Thread(target=self._run, name="speaker-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._jobs.put(None)
            self._thread.join(timeout)
            self._thread = None
