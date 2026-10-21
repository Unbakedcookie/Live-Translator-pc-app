"""Overlap splitting (2026-10-20): the decision logic with stand-in models (Tier A), and the
real ONNX models on a FLEURS mixture when they're installed."""

from pathlib import Path

import numpy as np
import pytest

from livetranslator.core import actions as a
from livetranslator.core.state import Source
from livetranslator.services.asr.worker import LineAudio
from livetranslator.services.speakers.separation import (
    FLAG_S,
    SAMPLE_RATE,
    SeparationSettings,
    SeparationWorker,
    enough_text,
    onset,
)

SECONDS = 4.0


def track(marker: float, start_s: float = 0.0) -> np.ndarray:
    """A stand-in voice: silence, then a constant level that names it (`marker`)."""
    audio = np.zeros(int(SECONDS * SAMPLE_RATE), dtype=np.float32)
    audio[int(start_s * SAMPLE_RATE) :] = marker
    return audio


class FakeDetector:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.calls = 0

    def overlap_seconds(self, audio: np.ndarray) -> float:
        self.calls += 1
        return self.seconds


class FakeSeparator:
    def __init__(self, tracks: list[np.ndarray] | None = None, fail: bool = False) -> None:
        self.tracks = tracks if tracks is not None else [track(0.2, 1.0), track(0.4, 0.0)]
        self.fail = fail

    def separate(self, audio: np.ndarray) -> list[np.ndarray]:
        if self.fail:
            raise RuntimeError("model broke")
        return self.tracks


TEXTS = {
    0.2: ("the second voice started later", "en"),
    0.4: ("the first voice spoke right away", "en"),
}


def transcribe_by_marker(texts=TEXTS, heard: list[tuple[str, ...]] | None = None):
    def transcribe(audio: np.ndarray, languages: tuple[str, ...]) -> tuple[str, str | None]:
        if heard is not None:
            heard.append(languages)
        return texts[round(float(audio.max()), 1)]

    return transcribe


def line(final: bool = True, seconds: float = SECONDS) -> LineAudio:
    audio = np.full(int(seconds * SAMPLE_RATE), 0.3, dtype=np.float32)
    return LineAudio("u1", audio, 10.0, 10.0 + seconds, final, (("hi", 0.0, 0.5),), "en")


def make(
    overlap: float = 2.0,
    separator: FakeSeparator | None = None,
    texts=TEXTS,
    enabled: bool = True,
    exists: bool = True,
    script: str = "simplified",
    others: tuple[str, ...] = (),
    heard: list[tuple[str, ...]] | None = None,
):
    emitted: list[a.Action] = []
    forwarded: list[LineAudio] = []
    worker = SeparationWorker(
        Path("unused"),
        transcribe_by_marker(texts, heard),
        emitted.append,
        forwarded.append,
        lambda _uid: exists,
        detector=FakeDetector(overlap),  # type: ignore[arg-type]
        separator=separator or FakeSeparator(),  # type: ignore[arg-type]
    )
    worker.configure(
        SeparationSettings(enabled=enabled, chinese_script=script, others_languages=others)  # type: ignore[arg-type]
    )
    return worker, emitted, forwarded


def test_separated_voices_follow_others_speak():
    """2026-10-20: "Others speak" limits the languages for split voices too."""
    heard: list[tuple[str, ...]] = []
    worker, _, _ = make(others=("zh", "en"), heard=heard)
    worker.submit(line())
    worker.run_pending()
    assert heard == [("zh", "en"), ("zh", "en")]


def test_an_overlapped_line_becomes_two_lines_with_their_own_voices():
    worker, emitted, forwarded = make()
    worker.submit(line())
    assert forwarded == []  # queued for the check, not passed on yet
    assert worker.run_pending() == 1
    update, add = emitted
    assert isinstance(update, a.UpdateUtterance) and update.utterance_id == "u1"
    assert update.fields["committed"] == "the first voice spoke right away"  # earlier onset
    assert update.fields["speaker_id"] == "others"  # relabelled from its own voice below
    assert isinstance(add, a.AddUtterance)
    second = add.utterance
    assert second.id == "u1-v2" and second.source is Source.OTHERS and second.is_final
    assert second.committed == "the second voice started later"
    assert (second.start, second.end) == (10.0, 14.0)
    assert [(f.utterance_id, round(float(f.audio.max()), 1), f.words) for f in forwarded] == [
        ("u1", 0.4, ()),  # speaker labels from each separated voice, no turn-splitting
        ("u1-v2", 0.2, ()),
    ]
    assert worker.splits == 1


def test_lines_pass_straight_through_when_theres_nothing_to_split():
    for case in (
        dict(enabled=False),  # setting off
        dict(overlap=FLAG_S - 0.1),  # one talker
    ):
        worker, emitted, forwarded = make(**case)  # type: ignore[arg-type]
        worker.submit(line())
        worker.run_pending()
        assert emitted == [] and [f.utterance_id for f in forwarded] == ["u1"], case
    worker, emitted, forwarded = make()
    worker.submit(line(final=False))  # partial lines are never held up
    assert [f.utterance_id for f in forwarded] == ["u1"] and worker.run_pending() == 0
    worker.submit(line(seconds=1.5))  # too short for two real turns
    worker.run_pending()
    assert emitted == [] and len(forwarded) == 2
    assert worker._detector.calls == 0  # type: ignore[attr-defined]


def test_a_split_that_doesnt_look_real_keeps_the_original_line():
    quiet = {0.2: ("", "en"), 0.4: ("the first voice spoke right away", "en")}
    same = {0.2: ("the first voice spoke right away", "en"), 0.4: ("the first voice spoke", "en")}
    cases = [
        dict(texts=quiet),  # one track had nobody in it
        dict(texts=same),  # the same voice leaked into both
        dict(separator=FakeSeparator([track(0.4)])),  # only one track came back
        dict(exists=False),  # the line was removed meanwhile (echo filter, clear)
        dict(separator=FakeSeparator(fail=True)),  # a model error never loses the label
    ]
    for case in cases:
        worker, emitted, forwarded = make(**case)  # type: ignore[arg-type]
        worker.submit(line())
        worker.run_pending()
        assert emitted == [], case
        assert [(f.utterance_id, f.words) for f in forwarded] == [("u1", (("hi", 0.0, 0.5),))]


def test_chinese_voices_follow_the_chosen_script():
    texts = {0.2: ("我們明天再玩", "zh"), 0.4: ("這個地圖很大", "zh")}
    worker, emitted, _ = make(texts=texts, script="simplified")
    worker.submit(line())
    worker.run_pending()
    assert emitted[0].fields["committed"] == "这个地图很大"  # type: ignore[attr-defined]
    assert emitted[1].utterance.committed == "我们明天再玩"  # type: ignore[attr-defined]


def test_helpers():
    assert enough_text("two words") and not enough_text("one")
    assert enough_text("你好吗") and not enough_text("你好")
    assert onset(track(0.5, 1.0)) == SAMPLE_RATE
    assert onset(np.zeros(10, dtype=np.float32)) == 10  # silent: sorts last


# ------------------------------------------------------------------ real models

MODELS = Path(r"D:\Live Translator pc app\local\app\data\models")
MIX = Path(r"D:\LiveTranslator\bench-data\separation\mixes\en-es-0-full-0db-c.wav")


@pytest.mark.skipif(
    not (MIX.exists() and (MODELS / "separation" / "convtasnet" / "model.onnx").exists()),
    reason="needs the separation models and the benchmark mixtures",
)
def test_real_models_find_and_split_an_overlap():
    from benchmarks.corpus import read_wav
    from livetranslator.services.speakers.separation import (
        OVERLAP_MODEL,
        SEPARATION_MODEL,
        OverlapDetector,
        Separator,
    )

    mix = read_wav(MIX)
    assert OverlapDetector(MODELS / OVERLAP_MODEL).overlap_seconds(mix) >= FLAG_S
    tracks = Separator(MODELS / SEPARATION_MODEL).separate(mix)
    assert len(tracks) == 2 and all(len(t) == len(mix) for t in tracks)
    level = float(np.sqrt(np.mean(np.square(mix))))
    for t in tracks:  # each voice comes back at the mix's loudness
        assert abs(float(np.sqrt(np.mean(np.square(t)))) - level) < 0.01
