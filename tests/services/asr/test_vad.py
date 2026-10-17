"""T043 — utterance segmentation (Tier A on hand-built frame sequences) + real Silero on a
FLEURS clip (integration, skipped when the corpus isn't downloaded).

Frames are 32 ms. Defaults: open at p >= 0.5, release below 0.35, close after
ceil(500 / 32) = 16 silent frames, hard cut at ceil(15000 / 32) = 469 frames, cut search
window ceil(2000 / 32) = 63 frames, pre-roll 3 frames.
"""

import numpy as np
import pytest

from livetranslator.core.state import VadConfig
from livetranslator.services.asr.vad import (
    FRAME,
    Segmenter,
    VadEvent,
    frame_energy,
    frames_for_ms,
)


def run(probs: list[float], energies: list[float] | None = None, config=None) -> list[VadEvent]:
    seg = Segmenter(config)
    events: list[VadEvent] = []
    for i, p in enumerate(probs):
        events += seg.push(p, energies[i] if energies else 0.1)
    return events + seg.flush()


def test_frame_math():
    assert frames_for_ms(500) == 16  # 500 / 32 = 15.6 -> 16
    assert frames_for_ms(15_000) == 469
    assert frames_for_ms(2_000) == 63


def test_silence_speech_silence():
    # 20 silent, 50 speech (frames 20..69), 20 silent
    probs = [0.02] * 20 + [0.9] * 50 + [0.02] * 20
    assert run(probs) == [
        VadEvent("open", 17),  # 20 - 3 pre-roll
        VadEvent("close", 70, "silence"),  # just after the last speech frame (69)
    ]


def test_short_pause_does_not_split():
    probs = [0.9] * 30 + [0.05] * 15 + [0.9] * 30 + [0.05] * 20  # 15 < 16 silent frames
    assert run(probs) == [VadEvent("open", 0), VadEvent("close", 75, "silence")]


def test_hysteresis_keeps_quiet_speech_open():
    probs = [0.9] * 10 + [0.4] * 40 + [0.05] * 20  # 0.4 >= release 0.35
    assert run(probs) == [VadEvent("open", 0), VadEvent("close", 50, "silence")]


def test_flush_closes_open_utterance():
    assert run([0.9] * 10) == [VadEvent("open", 0), VadEvent("close", 10, "flush")]


def test_hard_cut_at_lowest_energy_in_last_two_seconds():
    n = 469  # exactly the max length
    energies = [0.5] * n
    energies[450] = 0.01  # the quietest frame inside the last 63 frames (406..468)
    events = run([0.9] * n + [0.05] * 20, energies + [0.0] * 20)
    assert events[:3] == [
        VadEvent("open", 0),
        VadEvent("close", 450, "max_length"),
        VadEvent("open", 450, "max_length"),
    ]
    assert events[3] == VadEvent("close", 469, "silence")


def test_custom_config():
    events = run([0.9] * 5 + [0.0] * 4, config=VadConfig(end_silence_ms=100))  # 100/32 -> 4
    assert events == [VadEvent("open", 0), VadEvent("close", 5, "silence")]


def test_frame_energy():
    assert frame_energy(np.full(FRAME, 0.5, dtype=np.float32)) == pytest.approx(0.5)


def test_real_silero_on_speech_with_padding():
    from benchmarks.corpus import default_dest, read_wav
    from livetranslator.services.asr.vad import SileroVad

    clip = default_dest() / "fleurs" / "en" / "1510.wav"
    if not clip.exists():
        pytest.skip("benchmark corpus not downloaded")
    speech = read_wav(clip)
    silence = np.zeros(16000, dtype=np.float32)  # 1 s = 31.25 frames
    audio = np.concatenate([silence, speech, silence])
    audio = audio[: len(audio) // FRAME * FRAME]
    vad, seg = SileroVad(), Segmenter()
    events: list[VadEvent] = []
    probs = []
    for frame in audio.reshape(-1, FRAME):
        p = vad(frame)
        probs.append(p)
        events += seg.push(p, frame_energy(frame))
    events += seg.flush()
    assert max(probs[:28]) < 0.5  # leading digital silence is not speech
    opens = [e for e in events if e.kind == "open"]
    closes = [e for e in events if e.kind == "close"]
    assert opens and closes and len(opens) == len(closes)
    assert opens[0].sample >= 16000 - 3 * FRAME  # nothing opens inside the padding
    assert closes[-1].reason == "silence"  # trailing second of silence closes it
    assert closes[-1].sample <= len(audio) - 15 * FRAME
