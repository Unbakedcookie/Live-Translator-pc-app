"""ASR worker: VAD + streaming decode for the "Me" and "Others" streams (T045; spec §5.4, §6.4).

One thread owns the speech model and serves every stream:

1. **VAD** (cheap, ~0.1 ms per 32 ms frame): each stream's new audio is read from its ring
   buffer and run through Silero VAD + the Segmenter, which open and close utterances.
   (The spec's separate VAD thread is folded in here: VAD only falls behind by one decode,
   ~0.4 s, and one thread keeps the order of events deterministic.)
2. **One decode per iteration**, chosen by `next_job`:
   - closed utterances first (their final text is what people read), oldest first;
   - otherwise the open utterance that grew by at least the update interval, least recently
     served first; ties go to "Others" (what the user is waiting to read).
   When the GPU can't keep up, every stream simply gets decoded less often.
3. **LocalAgreement** turns partial decodes into committed + tentative text; the final
   decode (beam search) commits the rest. Results reach the store through `emit`
   (Store.dispatch, which is thread-safe).

Utterance times are on the app's monotonic clock: a sample's time is estimated when it is
read (time now minus the audio still unread behind it), because WASAPI loopback delivers no
data during silence, so sample counts alone don't track wall time.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from loguru import logger

from livetranslator.core import actions as a
from livetranslator.core.state import Source, StatusLevel, Utterance, VadConfig
from livetranslator.services.asr.base import SAMPLE_RATE, ASREngine, Audio, Transcription, Word
from livetranslator.services.asr.chinese import ChineseScript, is_chinese, to_script
from livetranslator.services.asr.language_choice import choose, others_candidates
from livetranslator.services.asr.local_agreement import LocalAgreement
from livetranslator.services.asr.vad import FRAME, Segmenter, VadEvent, frame_energy
from livetranslator.services.audio.ring import Float, RingBuffer
from livetranslator.services.timings import Timings, timed

Emit = Callable[[a.Action], None]


@dataclass(frozen=True)
class LineAudio:
    """An Others line's audio for speaker labels (T102/T105). Times on the app clock;
    `words` are (text, start, end) relative to the line start (final lines only)."""

    utterance_id: str
    audio: Float
    start: float
    end: float
    final: bool
    words: tuple[tuple[str, float, float], ...] = ()
    language: str | None = None


LineAudioFn = Callable[[LineAudio], None]


class VadFn(Protocol):
    """Streaming VAD: one FRAME in, speech probability out (SileroVad satisfies it)."""

    def __call__(self, frame: Float) -> float: ...

    def reset(self) -> None: ...


MIN_PARTIAL_S = 0.5  # Whisper guesses wildly on shorter audio
MIN_FINAL_S = 0.25
EARLY_LABEL_S = 1.5  # audio needed before a partial line gets a provisional speaker label
LANGUAGE_LOCK_P = 0.7  # "Others": keep the detected language once this sure
DETECT_SURE = 0.97  # Me in several languages: keep the pick once this sure (its share)
DETECT_MIN_S = 1.0  # ... and the line is at least this long
NO_SPEECH_P = 0.6  # drop a segment Whisper itself thinks is not speech...
LOW_LOGPROB = -1.0  # ...and decoded with low confidence (faster-whisper's own thresholds)
IDLE_S = 0.03
MAX_RESTARTS = 1  # spec §9: a crashed worker restarts once, then reports an error
FAILURES_BEFORE_ERROR = 5  # decodes failing in a row before the user is told
STATUS_KEY = "asr"
SOURCE_ORDER = {Source.OTHERS: 0, Source.ME: 1, Source.SCREEN: 2}
SPEAKER_IDS = {Source.ME: "me", Source.OTHERS: "others"}


@dataclass(frozen=True)
class AsrSettings:
    update_interval_s: float = 0.5
    # The languages the mic may be in: one = always that one; several = detect among them per
    # line; empty = detect any (speech_controller.mic_languages resolves the setting).
    mic_languages: tuple[str, ...] = ("en",)
    # The same for other people (Settings "Others speak", user request 2026-10-20): empty =
    # detect any language (the default), one = always that one, several = among those.
    others_languages: tuple[str, ...] = ()
    others_anything_else: bool = True  # listed languages preferred, any other still allowed
    vad: VadConfig = field(default_factory=VadConfig)
    enabled: frozenset[Source] = frozenset({Source.ME, Source.OTHERS})
    chinese_script: ChineseScript = "simplified"


@dataclass
class OpenUtterance:
    id: str
    source: Source
    start_sample: int
    start_time: float
    agreement: LocalAgreement = field(default_factory=LocalAgreement)
    decoded_to: int = 0  # end sample of the newest partial decode
    added: bool = False  # AddUtterance sent
    language: str | None = None  # locked language
    language_locked: bool = False  # Me in several languages: the pick is final
    end_sample: int | None = None
    end_time: float | None = None
    early_audio_sent: bool = False  # speaker labels: provisional fingerprint handed over


@dataclass
class StreamState:
    source: Source
    ring: RingBuffer
    vad: VadFn
    segmenter: Segmenter
    vad_origin: int = 0  # absolute sample of the segmenter's frame 0
    cursor: int = 0  # next sample not yet seen by the VAD
    open: OpenUtterance | None = None
    closed: deque[OpenUtterance] = field(default_factory=deque[OpenUtterance])
    last_served: float = 0.0


@dataclass(frozen=True)
class Job:
    stream: StreamState
    utterance: OpenUtterance
    final: bool


def next_job(streams: Sequence[StreamState], update_samples: int) -> Job | None:
    """The decode to run next (see module docstring, point 2). Pure: no side effects."""
    finals = [(u.end_time or 0.0, SOURCE_ORDER[s.source], s, u) for s in streams for u in s.closed]
    if finals:
        _, _, stream, utterance = min(finals, key=lambda f: (f[0], f[1]))
        return Job(stream, utterance, final=True)
    min_samples = int(MIN_PARTIAL_S * SAMPLE_RATE)
    ready = [
        s
        for s in streams
        if s.open is not None
        and s.cursor - s.open.decoded_to >= update_samples
        and s.cursor - s.open.start_sample >= min_samples
    ]
    if not ready:
        return None
    stream = min(ready, key=lambda s: (s.last_served, SOURCE_ORDER[s.source]))
    assert stream.open is not None  # nosec B101 - filtered above
    return Job(stream, stream.open, final=False)


def speech_words(result: Transcription) -> list[Word]:
    """Words of the segments that look like speech (drops Whisper's silence guesses)."""
    kept: list[Word] = []
    for segment in result.segments:
        no_speech = segment.no_speech_prob or 0.0
        logprob = segment.avg_logprob if segment.avg_logprob is not None else 0.0
        if no_speech > NO_SPEECH_P and logprob < LOW_LOGPROB:
            continue
        kept.extend(segment.words)
    return kept


class ASRWorker:
    def __init__(
        self,
        engine: ASREngine,
        emit: Emit,
        settings: AsrSettings | None = None,
        vad_factory: Callable[[], VadFn] | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_line_audio: LineAudioFn | None = None,
        timings: Timings | None = None,
    ) -> None:
        self._engine = engine
        self._timings = timings  # T091 readout: decode durations
        self._on_line_audio = on_line_audio
        self._emit = emit
        self._settings = settings or AsrSettings()
        self._vad_factory = vad_factory or _silero
        self._clock = clock
        self.streams: dict[Source, StreamState] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()  # streams/settings vs. the worker thread
        self.load_error: str | None = None
        self._decode_failures = 0

    # ------------------------------------------------------------ setup (any thread)

    def add_stream(self, source: Source, ring: RingBuffer) -> None:
        with self._lock:
            start = ring.total_written
            self.streams[source] = StreamState(
                source,
                ring,
                self._vad_factory(),
                Segmenter(self._settings.vad),
                vad_origin=start,
                cursor=start,
            )

    def remove_stream(self, source: Source) -> None:
        with self._lock:
            stream = self.streams.pop(source, None)
        if stream is not None and stream.open is not None and stream.open.added:
            self._emit(a.RemoveUtterance(stream.open.id))

    def configure(self, settings: AsrSettings) -> None:
        with self._lock:
            vad_changed = settings.vad != self._settings.vad
            self._settings = settings
            if vad_changed:
                for stream in self.streams.values():
                    self._restart_vad(stream)

    @property
    def settings(self) -> AsrSettings:
        return self._settings

    # ------------------------------------------------------------ one iteration

    def step(self) -> bool:
        """Advance the VAD on every stream and run at most one decode. True if it decoded."""
        with self._lock:
            settings = self._settings
            now = self._clock()
            for stream in self.streams.values():
                if stream.source in settings.enabled:
                    self._advance_vad(stream, now)
                else:
                    self._mute(stream, now)
            job = next_job(
                list(self.streams.values()), int(settings.update_interval_s * SAMPLE_RATE)
            )
            if job is None:
                return False
            job.stream.last_served = now
            if job.final:
                job.stream.closed.remove(job.utterance)
        try:
            if job.final:
                self._finalize(job, settings)
            else:
                self._partial(job, settings)
        except Exception as exc:  # one bad decode must not stop speech recognition
            logger.warning("ASR decode failed ({})", type(exc).__name__)
            if job.final and job.utterance.added:
                self._emit(a.RemoveUtterance(job.utterance.id))
            if not job.final:
                # Count this audio as tried: otherwise the same job is picked again at once,
                # forever (a 100 % CPU loop while e.g. the GPU driver is down).
                job.utterance.decoded_to = job.stream.cursor
            self._decode_failures += 1
            if self._decode_failures == FAILURES_BEFORE_ERROR:  # e.g. the GPU driver crashed
                self._status(
                    StatusLevel.ERROR,
                    "Speech recognition keeps failing. Restart the app; details are in the log.",
                )
            return True
        if self._decode_failures >= FAILURES_BEFORE_ERROR:
            self._status(*ready_status(self._engine))  # working again
        self._decode_failures = 0
        return True

    # ------------------------------------------------------------ VAD

    def _restart_vad(self, stream: StreamState) -> None:
        stream.vad = self._vad_factory()
        stream.segmenter = Segmenter(self._settings.vad)
        stream.vad_origin = stream.cursor

    def _time_of(self, stream: StreamState, sample: int, now: float) -> float:
        return now - (stream.ring.total_written - sample) / SAMPLE_RATE

    def _advance_vad(self, stream: StreamState, now: float) -> None:
        written = stream.ring.total_written
        if stream.cursor < stream.ring.oldest_available:
            # Fell more than the ring's length behind (the PC stalled): skip to live audio.
            self._close_open(stream, stream.cursor, now)
            stream.cursor = written
            self._restart_vad(stream)
            return
        frames = (written - stream.cursor) // FRAME
        if frames <= 0:
            return
        audio = stream.ring.read(stream.cursor, stream.cursor + frames * FRAME)
        for i in range(frames):
            frame = audio[i * FRAME : (i + 1) * FRAME]
            events = stream.segmenter.push(stream.vad(frame), frame_energy(frame))
            for event in events:
                self._on_vad_event(stream, event, now)
        stream.cursor += frames * FRAME

    def _on_vad_event(self, stream: StreamState, event: VadEvent, now: float) -> None:
        sample = stream.vad_origin + event.sample
        if event.kind == "close":
            self._close_open(stream, sample, now)
            if event.reason == "silence":
                # Silero's recurrent state, carried across a finished utterance, can leave
                # it deaf to the next one for seconds (measured: a Japanese FLEURS sentence
                # after another opened 2.6 s late). Between utterances there is only
                # silence, so starting fresh loses nothing.
                stream.vad.reset()
            return
        stream.open = OpenUtterance(
            id=f"{stream.source.value}-{uuid.uuid4().hex[:10]}",
            source=stream.source,
            start_sample=sample,
            start_time=self._time_of(stream, sample, now),
            decoded_to=sample,
        )

    def _close_open(self, stream: StreamState, sample: int, now: float) -> None:
        utterance = stream.open
        if utterance is None:
            return
        utterance.end_sample = max(sample, utterance.start_sample)
        utterance.end_time = self._time_of(stream, utterance.end_sample, now)
        stream.closed.append(utterance)
        stream.open = None

    def _mute(self, stream: StreamState, now: float) -> None:
        """Muted: finish the current line with what was heard, ignore everything after."""
        if stream.open is not None:
            self._close_open(stream, stream.cursor, now)
        if stream.cursor != stream.ring.total_written:
            stream.cursor = stream.ring.total_written
            self._restart_vad(stream)

    # ------------------------------------------------------------ decoding

    @staticmethod
    def _choices(source: Source, settings: AsrSettings) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(languages a stream may be in, preferred among them); () = Whisper detects any."""
        if source is Source.ME:
            return settings.mic_languages, ()
        if source is Source.OTHERS:
            return others_candidates(settings.others_languages, settings.others_anything_else)
        return (), ()

    @property
    def _can_detect(self) -> bool:
        return hasattr(self._engine, "detect_language")

    def _language(self, job: Job, settings: AsrSettings) -> str | None:
        languages, _preferred = self._choices(job.stream.source, settings)
        if len(languages) == 1:
            return languages[0]
        return job.utterance.language

    def _detect_among(
        self, job: Job, settings: AsrSettings, audio: Audio, final: bool = False
    ) -> None:
        """A stream in several known languages: the likeliest of *those* (Whisper scores
        every language). Checked on each partial until it's clearly sure, and always once
        more on the whole line before the final decode (measured 2026-10-19 on FLEURS es/en,
        zh/en, ja/en: sure (share >= 0.97, >= 1 s) was right 63 of 64 times, whole lines 80
        of 80; with 4 languages 72 of 72 whole lines)."""
        u = job.utterance
        languages, preferred = self._choices(job.stream.source, settings)
        if len(languages) < 2:
            return
        if u.language_locked and not final:
            return
        detect = getattr(self._engine, "detect_language", None)
        if detect is None:
            if not preferred and job.stream.source is Source.ME:  # no scores: the first one
                u.language, u.language_locked = languages[0], True
            return  # Others: the decode detects (as before "Others speak")
        scores = getattr(self._engine, "language_scores", None)
        with timed(self._timings, "asr"):
            if preferred and scores is not None:
                shares = scores(audio, languages)
                code = choose(shares, preferred)
                share = shares[code]  # a preferred pick behind the top one is never "sure"
            else:
                code, share = detect(audio, languages)
        u.language = str(code)
        u.language_locked = share >= DETECT_SURE and len(audio) >= DETECT_MIN_S * SAMPLE_RATE

    def _partial(self, job: Job, settings: AsrSettings) -> None:
        u, stream = job.utterance, job.stream
        end = stream.cursor
        audio = stream.ring.read(u.start_sample, end)
        self._detect_among(job, settings, audio)
        with timed(self._timings, "asr"):
            result = self._engine.transcribe(audio, language=self._language(job, settings))
        u.decoded_to = end
        if (
            u.language is None
            and (not self._choices(stream.source, settings)[0] or not self._can_detect)
            and (result.language_probability or 0.0) >= LANGUAGE_LOCK_P
        ):
            u.language = result.language
        state = u.agreement.update(speech_words(result))
        if not (state.committed or state.tentative):
            return
        language = self._language(job, settings) or result.language
        fields: dict[str, object] = {"committed": state.committed, "tentative": state.tentative}
        self._publish(u, fields, language)
        if (
            self._on_line_audio is not None
            and stream.source is Source.OTHERS
            and not u.early_audio_sent
            and len(audio) >= EARLY_LABEL_S * SAMPLE_RATE
        ):
            u.early_audio_sent = True
            end_time = u.start_time + len(audio) / SAMPLE_RATE
            self._on_line_audio(LineAudio(u.id, audio, u.start_time, end_time, False))

    def _finalize(self, job: Job, settings: AsrSettings) -> None:
        u, stream = job.utterance, job.stream
        end = u.end_sample if u.end_sample is not None else stream.cursor
        audio = stream.ring.read(u.start_sample, end)
        self._detect_among(job, settings, audio, final=True)
        if len(audio) < MIN_FINAL_S * SAMPLE_RATE:
            text = u.agreement.committed_text
            language = self._language(job, settings)
        else:
            with timed(self._timings, "asr"):
                result = self._engine.transcribe(
                    audio, language=self._language(job, settings), final=True
                )
            text = u.agreement.finalize(speech_words(result)).committed
            language = self._language(job, settings) or result.language
        if not text.strip():
            if u.added:
                self._emit(a.RemoveUtterance(u.id))
            return
        fields: dict[str, object] = {
            "committed": text,
            "tentative": "",
            "is_final": True,
            "end": u.end_time,
        }
        self._publish(u, fields, language)
        if self._on_line_audio is not None and stream.source is Source.OTHERS:
            end_time = u.end_time if u.end_time is not None else u.start_time
            self._on_line_audio(
                LineAudio(
                    u.id,
                    audio,
                    u.start_time,
                    end_time,
                    True,
                    u.agreement.committed_words,
                    language,
                )
            )

    def _publish(self, u: OpenUtterance, fields: dict[str, object], language: str | None) -> None:
        if language is not None:
            fields["language"] = language
        if is_chinese(language):  # one script, whatever Whisper wrote (Mandarin follow-up)
            script = self._settings.chinese_script
            for key in ("committed", "tentative"):
                value = fields.get(key)
                if isinstance(value, str):
                    fields[key] = to_script(value, script)
        if u.added:
            self._emit(a.UpdateUtterance(u.id, fields))
            return
        self._emit(
            a.AddUtterance(
                Utterance(
                    id=u.id,
                    source=u.source,
                    speaker_id=SPEAKER_IDS.get(u.source, u.source.value),
                    start=u.start_time,
                    **fields,  # pyright: ignore[reportArgumentType]
                )
            )
        )
        u.added = True

    # ------------------------------------------------------------ thread

    def _status(self, level: StatusLevel, message: str) -> None:
        self._emit(a.SetStatus(STATUS_KEY, level, message))

    def _load(self) -> bool:
        if self._engine.is_loaded:
            return True
        self._status(StatusLevel.BUSY, "Loading the speech model…")
        try:
            self._engine.load()
        except Exception as exc:
            self.load_error = f"{type(exc).__name__}: {exc}"
            logger.error("speech model failed to load ({})", type(exc).__name__)
            missing = "not downloaded" in str(exc)
            self._status(
                StatusLevel.ERROR,
                "The speech model isn't downloaded. Settings, Advanced, Run setup gets it."
                if missing
                else "The speech model couldn't be loaded, so speech isn't recognised. "
                "Details are in the log.",
            )
            return False
        self._status(*ready_status(self._engine))
        return True

    def _run(self) -> None:
        if not self._load():
            return
        restarts = 0
        while not self._stop.is_set():
            try:
                if not self.step():
                    self._stop.wait(IDLE_S)
            except Exception as exc:  # spec §9: restart once, then stop with an error status
                logger.error("speech worker crashed ({})", type(exc).__name__)
                if restarts >= MAX_RESTARTS:
                    self._status(
                        StatusLevel.ERROR,
                        "Speech recognition stopped after an error. Restart the app; "
                        "details are in the log.",
                    )
                    return
                restarts += 1
                self._reset_streams()
                self._status(StatusLevel.WARNING, "Speech recognition hit an error and restarted.")

    def _reset_streams(self) -> None:
        """Drop half-finished lines after a crash; capture continues from 'now'."""
        with self._lock:
            sources = [(s.source, s.ring) for s in self.streams.values()]
        for source, ring in sources:
            self.remove_stream(source)  # also removes a shown half-finished line
            self.add_stream(source, ring)  # fresh VAD + segmenter from "now"

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("ASR worker already started")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="asr-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None


def _silero() -> VadFn:
    from livetranslator.services.asr.vad import SileroVad

    return SileroVad()


def ready_status(engine: object) -> tuple[StatusLevel, str]:
    """What to say once the model is loaded (spec §5.4, §9: CPU fallback gets a notice)."""
    device = getattr(engine, "device_used", None)
    if getattr(engine, "gpu_error", None):
        return (
            StatusLevel.WARNING,
            "Your graphics card couldn't run speech recognition, so it runs on the processor "
            "with a smaller model (slower, a little less accurate). Details are in the log.",
        )
    if device == "cpu":
        return (
            StatusLevel.WARNING,
            "No NVIDIA graphics card found: speech runs on the processor with a smaller model "
            "(slower, a little less accurate).",
        )
    return StatusLevel.OK, "Speech recognition is ready."
