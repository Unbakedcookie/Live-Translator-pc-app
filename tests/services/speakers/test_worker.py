"""T102 — speaker worker plumbing (fake embedder) and a real-model run on the T035 mix."""

import math
import os
from pathlib import Path

import numpy as np
import pytest

from livetranslator.core import actions as a
from livetranslator.core.state import SpeakerMode, StatusLevel
from livetranslator.services.speakers.base import SAMPLE_RATE, SpeakerEmbedder
from livetranslator.services.speakers.fusion import SpeakingInterval
from livetranslator.services.speakers.worker import LabelJob, SpeakerSettings, SpeakerWorker


class FakeEmbedder:
    """The audio's first sample encodes the voice as an angle in degrees."""

    name = "fake"

    def __init__(self, fail: bool = False) -> None:
        self.loaded = False
        self.fail = fail
        self.calls = 0

    @property
    def is_loaded(self) -> bool:
        return self.loaded

    def load(self) -> None:
        if self.fail:
            raise RuntimeError("model missing")
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def embed(self, audio):
        self.calls += 1
        r = math.radians(float(audio[0]))
        return np.array([math.cos(r), math.sin(r)], dtype=np.float32)


def voice(degrees: float, seconds: float = 2.0) -> np.ndarray:
    return np.full(int(seconds * SAMPLE_RATE), degrees, dtype=np.float32)


def job(uid: str, degrees: float, final: bool = True, seconds: float = 2.0, start=0.0) -> LabelJob:
    return LabelJob(uid, voice(degrees, seconds), start, start + seconds, final)


def make(mode=SpeakerMode.AUTO, embedder=None, intervals=None):
    emitted: list[a.Action] = []
    worker = SpeakerWorker(
        embedder or FakeEmbedder(), emitted.append, SpeakerSettings(mode=mode), intervals
    )
    return worker, emitted


def labels(emitted) -> list[tuple[str, object]]:
    return [
        (x.utterance_id, x.fields["speaker_id"])
        for x in emitted
        if isinstance(x, a.UpdateUtterance)
    ]


def test_final_lines_get_stable_voice_labels():
    worker, emitted = make()
    for uid, angle in (("u1", 0), ("u2", 90), ("u3", 10), ("u4", 95)):
        worker.handle(job(uid, angle))
    assert labels(emitted) == [
        ("u1", "voice:0"),
        ("u2", "voice:1"),
        ("u3", "voice:0"),
        ("u4", "voice:1"),
    ]


def test_partial_lines_only_peek():
    worker, emitted = make()
    worker.handle(job("p1", 0, final=False))  # nobody known: no label, nothing learned
    assert labels(emitted) == [] and worker.clusters.count == 0
    worker.handle(job("u1", 0))
    worker.handle(job("p2", 15, final=False))
    worker.handle(job("p3", 90, final=False))  # unknown voice: wait for the final
    assert labels(emitted) == [("u1", "voice:0"), ("p2", "voice:0")]
    assert worker.clusters.count == 1


def test_short_lines_and_off_mode_are_skipped():
    embedder = FakeEmbedder()
    worker, emitted = make(embedder=embedder)
    worker.handle(job("tiny", 0, seconds=0.3))
    assert labels(emitted) == [] and embedder.calls == 0
    worker.handle(job("short", 0, seconds=0.8))  # embedded, but < 1 s -> "others"
    assert labels(emitted) == [("short", "others")]
    off, off_emitted = make(SpeakerMode.OFF)
    off.submit(job("u1", 0))
    assert off.run_pending() == 0 and off_emitted == []


def test_discord_name_wins_and_teaches_the_voice():
    def intervals(start: float, end: float):
        return [SpeakingInterval("mika", start, end)] if start < 5 else []

    worker, emitted = make(intervals=intervals)
    worker.handle(job("u1", 0, start=0.0))  # Discord says mika -> vote voice 0 = mika
    worker.handle(job("u2", 5, start=10.0))  # no Discord data -> voice label
    assert labels(emitted) == [("u1", "discord:mika"), ("u2", "voice:0")]
    voice_only, voice_emitted = make(SpeakerMode.VOICE, intervals=intervals)
    voice_only.handle(job("u1", 0, start=0.0))
    assert labels(voice_emitted) == [("u1", "voice:0")]  # Discord ignored in voice mode


def test_load_failure_turns_labels_off_with_a_status():
    worker, emitted = make(embedder=FakeEmbedder(fail=True))
    worker.handle(job("u1", 0))
    statuses = [x for x in emitted if isinstance(x, a.SetStatus)]
    assert statuses and statuses[0].level is StatusLevel.WARNING
    assert not worker.enabled
    worker.submit(job("u2", 0))
    assert worker.run_pending() == 0


def test_reset_forgets_voices_and_votes():
    worker, emitted = make()
    worker.handle(job("u1", 0))
    worker.reset()
    worker.handle(job("u2", 90))
    assert labels(emitted)[-1] == ("u2", "voice:0")  # numbering starts again


def test_thread_processes_jobs():
    worker, emitted = make()
    worker.start()
    try:
        worker.submit(job("u1", 0))
    finally:
        worker.stop()
    assert labels(emitted) == [("u1", "voice:0")]
    assert isinstance(FakeEmbedder(), SpeakerEmbedder)


BENCH = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data"))
TITANET = BENCH / "models" / "diarization" / "nemo_en_titanet_large.onnx"


@pytest.mark.skipif(not TITANET.is_file(), reason="TitaNet model not on this PC")
def test_real_model_on_the_t035_three_speaker_mix(tmp_path: Path):
    from benchmarks.corpus import default_dest
    from benchmarks.diar_bench import MIXES, build_mix, vad_utterances
    from benchmarks.diar_metrics import der
    from livetranslator.services.speakers.sherpa_engine import FOLDER, SherpaEmbedder

    models = tmp_path / "models"
    (models / FOLDER).mkdir(parents=True)
    (models / FOLDER / TITANET.name).write_bytes(TITANET.read_bytes())
    before = {p for p in tmp_path.rglob("*")}
    mix = build_mix(MIXES[2], default_dest() / "diarization")  # 3 speakers, es
    worker, emitted = make(embedder=SherpaEmbedder(models))
    spans = vad_utterances(mix.audio)
    for i, (start, end) in enumerate(spans):
        worker.handle(LabelJob(f"u{i}", mix.audio[start:end], start / 16000, end / 16000, True))
    by_id = dict(labels(emitted))
    hyp = [
        (start / 16000, end / 16000, str(by_id[f"u{i}"]))
        for i, (start, end) in enumerate(spans)
        if f"u{i}" in by_id
    ]
    # M03 (T035, diarization.json) per-line DER on this mix: 0.113 at similarity 0.5 and 0.6.
    # Acceptance: within 10 % of it (+ half a 10 ms grid step of rounding slack).
    result = der(mix.turns, hyp)
    assert result.der <= 0.113 * 1.1 + 0.005, result
    assert {p for p in tmp_path.rglob("*")} == before  # no fingerprint ever written (D-028)
