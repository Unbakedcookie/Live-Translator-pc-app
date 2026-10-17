"""T035 — DER and turn accuracy on toy cases computed by hand."""

import pytest

from benchmarks.diar_metrics import best_mapping, der, turn_accuracy

REF = [(0.0, 2.0, "A"), (2.0, 4.0, "B")]


def test_perfect_hypothesis_with_other_label_names():
    result = der(REF, [(0.0, 2.0, "1"), (2.0, 4.0, "0")], collar=0.0)
    assert result.der == 0.0
    assert result.mapping == {"1": "A", "0": "B"}


def test_late_turn_change_is_confusion():
    # Hyp switches at 2.5 s instead of 2.0 s: 0.5 s of B is labelled as A's speaker.
    # Reference speech = 4.0 s -> confusion 0.5 / 4.0 = 12.5 %.
    result = der(REF, [(0.0, 2.5, "x"), (2.5, 4.0, "y")], collar=0.0)
    assert result.confusion == pytest.approx(0.125, abs=0.003)
    assert result.miss == 0.0 and result.false_alarm == 0.0


def test_collar_forgives_boundary_jitter():
    # Same hypothesis, collar 0.25: frames 1.75-2.25 are ignored around the 2.0 boundary
    # (plus 0-0.25 and 3.75-4.0 at the outer edges). Remaining confusion: 2.25-2.5 = 0.25 s.
    # Scored reference: 4.0 - 0.25 - 0.5 - 0.25 = 3.0 s -> 0.25 / 3.0 = 8.3 %.
    result = der(REF, [(0.0, 2.5, "x"), (2.5, 4.0, "y")], collar=0.25)
    assert result.confusion == pytest.approx(0.25 / 3.0, abs=0.004)


def test_miss_and_false_alarm():
    # Hyp misses 3.0-4.0 (1 s of B) and invents speech at 4.0-5.0.
    # miss = 1/4 = 25 %, false alarm = 1/4 = 25 %, DER = 50 %.
    result = der(REF, [(0.0, 2.0, "a"), (2.0, 3.0, "b"), (4.0, 5.0, "b")], collar=0.0)
    assert result.miss == pytest.approx(0.25, abs=0.003)
    assert result.false_alarm == pytest.approx(0.25, abs=0.003)
    assert result.der == pytest.approx(0.5, abs=0.005)


def test_extra_hypothesis_speaker_counts_as_confusion():
    # Speaker A split into two hyp labels: the smaller part (0-0.5 s) can't map to A.
    result = der(REF, [(0.0, 0.5, "p"), (0.5, 2.0, "q"), (2.0, 4.0, "r")], collar=0.0)
    assert result.mapping == {"q": "A", "r": "B"}
    assert result.confusion == pytest.approx(0.5 / 4.0, abs=0.003)


def test_best_mapping_is_one_to_one():
    # One hyp label covering both speakers maps to the one it overlaps most (A: 2 s, B: 1 s).
    assert best_mapping(REF, [(0.0, 3.0, "z")]) == {"z": "A"}
    assert best_mapping([(0.0, 1.0, "A"), (1.0, 4.0, "B")], [(0.0, 4.0, "z")]) == {"z": "B"}


def test_turn_accuracy():
    ref = [(0.0, 1.0, "A"), (1.0, 2.0, "B"), (2.0, 3.0, "A"), (3.0, 4.0, "C")]
    # Labels: A->0, B->1, A->0, C->1 (wrong: merged with B). 3 of 4 right after mapping.
    accuracy, mapping = turn_accuracy(ref, ["0", "1", "0", "1"])
    assert accuracy == 0.75
    assert mapping["0"] == "A"
    assert turn_accuracy(ref, [None, None, None, None])[0] == 0.0
