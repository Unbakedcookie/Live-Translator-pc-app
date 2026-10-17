"""T105 — speaker change inside a line: window-label runs and word snapping (Tier A)."""

import pytest

from livetranslator.services.speakers.change import (
    find_change,
    runs,
    snap_to_words,
    window_center,
    window_starts,
)


def labels(text: str) -> list[str | None]:
    return [None if ch == "?" else ch for ch in text]


def test_runs():
    assert [(r.label, r.first, r.last) for r in runs(labels("11?22"))] == [
        ("1", 0, 1),
        (None, 2, 2),
        ("2", 3, 4),
    ]


@pytest.mark.parametrize(
    "pattern",
    ["0000000000", "000000000?", "???????", "??000?", "2?22", "1111", "0?0?0", ""],
)
def test_single_speaker_patterns_from_t035_never_split(pattern):
    # Every one of these is a real single-speaker line from the T035 mixes (or a variant).
    assert find_change(labels(pattern)) is None


def test_known_speaker_then_unclear_stretch_splits_where_the_first_stops():
    # "11111?????22" (the real T035 4-speaker line; true change at 3.42 s): the 5 unclear
    # windows are a run of their own, so the change is where speaker 1 stops being
    # recognised: centres 4*0.5+0.75 = 2.75 and 5*0.5+0.75 = 3.25 -> 3.0 s (word snapping
    # refines it). Halfway to speaker 2's run would have been 4.25 s, further off.
    assert find_change(labels("11111?????22")) == pytest.approx(3.0)


def test_two_known_speakers_back_to_back():
    # "111222": centres 2*0.5+0.75 = 1.75 and 3*0.5+0.75 = 2.25 -> 2.0 s.
    assert find_change(labels("111222")) == pytest.approx(2.0)


def test_new_voice_then_known_speaker():
    # "???000": unclear run 0-2 (new voice), known 0 from window 3.
    # Centres 2*0.5+0.75 = 1.75 and 3*0.5+0.75 = 2.25 -> 2.0 s.
    assert find_change(labels("???000")) == pytest.approx(2.0)
    assert find_change(labels("000???")) == pytest.approx(2.0)  # known, then a new voice


def test_short_runs_are_noise():
    assert find_change(labels("11112")) is None  # 1 window of "2" is not a run
    assert find_change(labels("??1111")) is None  # 2 unclear windows are not a new voice


def test_snap_to_the_nearest_word_gap():
    words = [(0.0, 0.4), (0.5, 1.0), (1.1, 1.9), (2.3, 2.8), (2.9, 3.5)]
    # Gaps at 0.45, 1.05, 2.1, 2.85. Estimate 2.0 -> 2.1 (the pause between turns).
    assert snap_to_words(2.0, words) == pytest.approx(2.1)
    assert snap_to_words(5.0, words) == 5.0  # no gap within 0.8 s: keep the estimate
    assert snap_to_words(1.0, []) == 1.0


def test_window_geometry():
    assert window_center(0) == 0.75
    assert window_starts(3.0) == [0.0, 0.5, 1.0, 1.5]
    assert window_starts(1.2) == []
