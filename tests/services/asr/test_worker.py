"""T045 — ASR worker: scheduling, utterance lifecycle, language, mute (fake engine + fake VAD).

Synthetic audio: silence = 0.0, "speech" = constant 0.5. The fake VAD calls a frame speech
when its mean |amplitude| > 0.1. The fake engine emits one word per started 0.5 s of audio
(" w0", " w1", ...), language "es" with probability 0.9, and records every call.
"""

import numpy as np
import pytest

from livetranslator.core import actions as a
from livetranslator.core.state import AppState, Source, StatusLevel
from livetranslator.core.store import Store
from livetranslator.services.asr.base import SAMPLE_RATE, Segment, Transcription, Word
from livetranslator.services.asr.vad import FRAME, Segmenter
from livetranslator.services.asr.worker import (
    AsrSettings,
    ASRWorker,
    Job,
    OpenUtterance,
    StreamState,
    next_job,
    speech_words,
)
from livetranslator.services.audio.ring import RingBuffer

SPEECH = 0.5


class FakeEngine:
    name = "fake"

    def __init__(self, language: str = "es", probability: float = 0.9) -> None:
        self.calls: list[tuple[int, str | None, bool]] = []
        self._language = language
        self._probability = probability
        self.loaded = False

    @property
    def is_loaded(self) -> bool:
        return self.loaded

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def transcribe(self, audio, *, language=None, prompt=None, final=False) -> Transcription:
        self.calls.append((len(audio), language, final))
        seconds = len(audio) / SAMPLE_RATE
        words = tuple(
            Word(f" w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(int(seconds / 0.5))
        )
        segment = Segment("".join(w.text for w in words), 0.0, seconds, words, -0.2, 0.01)
        return Transcription((segment,), language or self._language, self._probability)


class FakeVad:
    def __init__(self) -> None:
        self.resets = 0

    def __call__(self, frame) -> float:
        return 1.0 if float(np.abs(frame).mean()) > 0.1 else 0.0

    def reset(self) -> None:
        self.resets += 1


def fake_vad() -> FakeVad:
    return FakeVad()


def tone(seconds: float, level: float) -> np.ndarray:
    return np.full(int(seconds * SAMPLE_RATE), level, dtype=np.float32)


NOW = [100.0]  # test clock: advanced by `feed` as audio "arrives" in real time


def adds(emitted: list[a.Action]) -> list[a.AddUtterance]:
    return [x for x in emitted if isinstance(x, a.AddUtterance)]


def last_fields(emitted: list[a.Action]) -> dict[str, object]:
    updates = [x for x in emitted if isinstance(x, a.UpdateUtterance)]
    return dict(updates[-1].fields)


def job_of(streams: list[StreamState]) -> Job:
    job = next_job(streams, 8000)
    assert job is not None
    return job


def make_worker(engine=None, **settings):
    emitted: list[a.Action] = []
    worker = ASRWorker(
        engine or FakeEngine(),
        emitted.append,
        AsrSettings(**settings),
        vad_factory=fake_vad,
        clock=lambda: NOW[0],
    )
    return worker, emitted


def drain(worker: ASRWorker) -> None:
    while worker.step():
        pass


def feed(worker, ring, chunks):
    for seconds, level in chunks:
        ring.write(tone(seconds, level))
        NOW[0] += seconds
        drain(worker)


def test_partials_then_final_for_one_utterance():
    engine = FakeEngine()
    worker, emitted = make_worker(engine)
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    feed(worker, ring, [(0.32, 0.0)] + [(0.25, SPEECH)] * 8 + [(0.25, 0.0)] * 4)
    kinds = [type(x).__name__ for x in emitted]
    assert kinds[0] == "AddUtterance" and kinds.count("AddUtterance") == 1
    assert all(k == "UpdateUtterance" for k in kinds[1:])
    added = adds(emitted)[0].utterance
    assert added.source is Source.OTHERS and added.speaker_id == "others"
    final = last_fields(emitted)
    assert final["is_final"] is True and final["tentative"] == ""
    # Speech covers samples 5120..37120. Open: first speech frame 10 minus 3 frames of
    # pre-roll -> sample 3584. Frame 72 (36864..37376) is half speech -> still speech, so
    # the close lands at frame 73 = sample 37376: 33792 samples = 2.112 s -> 4 words.
    assert final["committed"] == "w0 w1 w2 w3"
    assert final["language"] == "es"
    final_calls = [c for c in engine.calls if c[2]]
    assert final_calls == [(33792, "es", True)]  # language locked from the partials
    # Times come from the clock at read time: duration matches the audio (2.112 s).
    end = final["end"]
    assert isinstance(end, float)
    vad = worker.streams[Source.OTHERS].vad
    assert isinstance(vad, FakeVad) and vad.resets == 1  # fresh VAD state after the line
    assert end - added.start == pytest.approx(33792 / SAMPLE_RATE)


def test_me_is_decoded_in_my_language():
    engine = FakeEngine(language="xx")
    worker, emitted = make_worker(engine, my_language="de")
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.ME, ring)
    feed(worker, ring, [(0.25, SPEECH)] * 6 + [(0.25, 0.0)] * 4)
    assert engine.calls and all(lang == "de" for _, lang, _ in engine.calls)
    assert adds(emitted)[0].utterance.speaker_id == "me"
    assert last_fields(emitted)["language"] == "de"


def test_others_language_is_not_locked_when_unsure():
    engine = FakeEngine(probability=0.5)  # below LANGUAGE_LOCK_P
    worker, _ = make_worker(engine)
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    feed(worker, ring, [(0.25, SPEECH)] * 6 + [(0.25, 0.0)] * 4)
    assert all(lang is None for _, lang, _ in engine.calls)


def test_short_noise_is_dropped_and_added_line_removed():
    # 0.32 s of "speech": too short for a partial (< 0.5 s) and the fake engine finds no
    # words in it, so nothing is ever shown.
    worker, emitted = make_worker()
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    feed(worker, ring, [(0.32, SPEECH), (0.8, 0.0)])
    assert emitted == []
    # A line that was shown but whose final decode is empty is taken back.
    u = OpenUtterance("x", Source.OTHERS, 0, 0.0, added=True, end_sample=FRAME * 20)
    stream = worker.streams[Source.OTHERS]
    ring.write(tone(1.0, 0.0))
    stream.closed.append(u)
    worker._engine.transcribe = lambda *args, **kw: Transcription(())
    worker.step()
    assert emitted[-1] == a.RemoveUtterance("x")


def test_mute_finishes_the_line_and_ignores_later_audio():
    worker, emitted = make_worker()
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.ME, ring)
    feed(worker, ring, [(0.25, SPEECH)] * 6)
    assert worker.streams[Source.ME].open is not None
    worker.configure(AsrSettings(enabled=frozenset({Source.OTHERS})))
    feed(worker, ring, [(0.25, SPEECH)] * 4)
    assert last_fields(emitted)["is_final"] is True
    assert worker.streams[Source.ME].open is None
    count = len(emitted)
    feed(worker, ring, [(0.5, SPEECH)] * 4)
    assert len(emitted) == count  # muted: nothing new


def stream(source: Source, cursor: int, open_from: int, decoded_to: int = 0) -> StreamState:
    s = StreamState(source, RingBuffer(1, SAMPLE_RATE), fake_vad(), Segmenter(), cursor=cursor)
    s.open = OpenUtterance(f"{source}", source, open_from, 0.0, decoded_to=decoded_to)
    return s


def test_next_job_is_fair_and_prefers_others_on_ties():
    me = stream(Source.ME, 20000, 0, decoded_to=10000)
    others = stream(Source.OTHERS, 20000, 0, decoded_to=10000)
    assert job_of([me, others]).stream is others  # tie -> Others
    others.last_served = 5.0
    assert job_of([me, others]).stream is me  # least recently served
    assert me.open is not None and others.open is not None
    me.open.decoded_to = 15000  # grew by 5000 < the 8000-sample interval: not ready
    assert job_of([me, others]).stream is others
    others.open.start_sample = 19000  # only 1000 samples of audio: below 0.5 s minimum
    assert next_job([me, others], 8000) is None


def test_finals_come_first_oldest_first():
    me = stream(Source.ME, 20000, 0)
    others = stream(Source.OTHERS, 20000, 0)
    late = OpenUtterance("late", Source.OTHERS, 0, 0.0, end_sample=10, end_time=5.0)
    early = OpenUtterance("early", Source.ME, 0, 0.0, end_sample=10, end_time=4.0)
    others.closed.append(late)
    me.closed.append(early)
    job = job_of([me, others])
    assert job.final and job.utterance is early
    me.closed.clear()
    assert job_of([me, others]).utterance is late


def test_speech_words_drops_segments_whisper_calls_silence():
    w = Word(" hi", 0.0, 0.3)
    keep = Segment(" hi", 0.0, 0.3, (w,), avg_logprob=-0.3, no_speech_prob=0.9)
    drop = Segment(" uh", 0.3, 0.6, (Word(" uh", 0.3, 0.6),), -1.5, 0.8)
    assert speech_words(Transcription((keep, drop))) == [w]


@pytest.mark.parametrize("fails", [False, True])
def test_thread_loads_engine_and_feeds_the_store(qtbot, fails):
    store = Store(AppState())
    engine = FakeEngine()
    if fails:
        engine.load = lambda: (_ for _ in ()).throw(RuntimeError("no model"))
    worker = ASRWorker(engine, store.dispatch, vad_factory=fake_vad)
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    worker.start()
    try:
        if fails:
            qtbot.waitUntil(
                lambda: (
                    "asr" in store.state.runtime.statuses
                    and store.state.runtime.statuses["asr"].level is StatusLevel.ERROR
                ),
                timeout=5000,
            )
            return
        qtbot.waitUntil(lambda: engine.loaded, timeout=5000)
        ring.write(tone(2.0, SPEECH))
        ring.write(tone(1.0, 0.0))
        qtbot.waitUntil(
            lambda: any(u.is_final for u in store.state.session.utterances), timeout=5000
        )
    finally:
        worker.stop()
    final = store.state.session.utterances[-1]
    assert final.committed.startswith("w0") and final.language == "es"
    assert store.state.runtime.statuses["asr"].level is StatusLevel.OK


def test_others_line_audio_is_handed_over_early_and_final():
    # T102 hook: one provisional hand-over once >= 1.5 s of audio was decoded, one at the end;
    # never for the mic.
    handed: list[tuple[str, int, bool]] = []
    emitted: list[a.Action] = []
    worker = ASRWorker(
        FakeEngine(),
        emitted.append,
        AsrSettings(),
        vad_factory=fake_vad,
        clock=lambda: NOW[0],
        on_line_audio=lambda line: handed.append((line.utterance_id, len(line.audio), line.final)),
    )
    others, me = RingBuffer(60, SAMPLE_RATE), RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, others)
    worker.add_stream(Source.ME, me)
    for _ in range(12):
        others.write(tone(0.25, SPEECH))
        me.write(tone(0.25, SPEECH))
        NOW[0] += 0.25
        drain(worker)
    for _ in range(4):
        others.write(tone(0.25, 0.0))
        me.write(tone(0.25, 0.0))
        NOW[0] += 0.25
        drain(worker)
    others_id = next(
        x.utterance.id
        for x in emitted
        if isinstance(x, a.AddUtterance) and x.utterance.source is Source.OTHERS
    )
    assert [h[0] for h in handed] == [others_id, others_id]
    assert [h[2] for h in handed] == [False, True]
    assert handed[0][1] >= 1.5 * SAMPLE_RATE


class ChineseEngine(FakeEngine):
    """Whisper writing Mandarin with Traditional characters mixed in."""

    def __init__(self, chars: str) -> None:
        super().__init__(language="zh", probability=0.95)
        self._chars = chars

    def transcribe(self, audio, *, language=None, prompt=None, final=False) -> Transcription:
        self.calls.append((len(audio), language, final))
        seconds = len(audio) / SAMPLE_RATE
        n = min(int(seconds / 0.5), len(self._chars))
        words = tuple(Word(self._chars[i], i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(n))
        segment = Segment("".join(w.text for w in words), 0.0, seconds, words, -0.2, 0.01)
        return Transcription((segment,), "zh", self._probability)


@pytest.mark.parametrize(
    ("script", "heard", "shown", "absent"),
    [("simplified", "門鍵這", "门键这", "門"), ("traditional", "门键这", "門鍵這", "门")],
)
def test_mandarin_is_written_in_one_script(script, heard, shown, absent):
    worker, emitted = make_worker(ChineseEngine(heard), chinese_script=script)
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    feed(worker, ring, [(0.32, 0.0)] + [(0.25, SPEECH)] * 8 + [(0.25, 0.0)] * 4)
    final = last_fields(emitted)
    text = str(final["committed"]).replace(" ", "")
    assert final["language"] == "zh" and text.startswith(shown[:2]) and absent not in text
    texts = [
        str(x.fields.get("committed", "")) for x in emitted if isinstance(x, a.UpdateUtterance)
    ]
    assert all(absent not in t for t in texts)  # partials too


def test_a_crash_restarts_once_then_reports_an_error(qtbot):
    """Spec §9: worker threads restart once, then show an error status."""
    worker, emitted = make_worker()
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    crashes: list[int] = []

    def broken_vad(stream, now) -> None:
        crashes.append(1)
        raise RuntimeError("bug outside a decode")

    worker._advance_vad = broken_vad  # type: ignore[method-assign]
    worker.start()
    try:
        qtbot.waitUntil(lambda: len(crashes) >= 2, timeout=3000)
        qtbot.wait(100)
    finally:
        worker.stop()
    messages = [(x.level, x.message) for x in emitted if isinstance(x, a.SetStatus)]
    assert (StatusLevel.WARNING, "Speech recognition hit an error and restarted.") in messages
    assert messages[-1][0] is StatusLevel.ERROR and "stopped" in messages[-1][1]
    assert len(crashes) == 2  # restarted once, then gave up


def test_decodes_failing_in_a_row_are_reported_and_cleared():
    class Flaky(FakeEngine):
        broken = True

        def transcribe(self, audio, *, language=None, prompt=None, final=False):
            if self.broken:
                raise RuntimeError("CUDA went away")
            return super().transcribe(audio, language=language, prompt=prompt, final=final)

    engine = Flaky()
    worker, emitted = make_worker(engine, update_interval_s=0.25)
    ring = RingBuffer(60, SAMPLE_RATE)
    worker.add_stream(Source.OTHERS, ring)
    feed(worker, ring, [(0.32, 0.0)] + [(0.25, SPEECH)] * 12)
    statuses = [x for x in emitted if isinstance(x, a.SetStatus)]
    assert statuses and statuses[-1].level is StatusLevel.ERROR
    engine.broken = False
    feed(worker, ring, [(0.25, SPEECH)] * 4)
    statuses = [x for x in emitted if isinstance(x, a.SetStatus)]
    assert statuses[-1].level is StatusLevel.OK  # working again


def test_ready_status_mentions_the_cpu_fallback():
    from livetranslator.services.asr.worker import ready_status

    class Engine:
        device_used: str | None = "cuda"
        gpu_error: str | None = None

    assert ready_status(Engine()) == (StatusLevel.OK, "Speech recognition is ready.")
    Engine.device_used = "cpu"
    assert ready_status(Engine())[0] is StatusLevel.WARNING
    Engine.gpu_error = "RuntimeError: cudnn missing"
    assert "graphics card couldn't" in ready_status(Engine())[1]
