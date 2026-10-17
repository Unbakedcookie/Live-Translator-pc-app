"""T101 — speaker fusion and lag calibration on hand-built timelines (Tier A)."""

from collections import Counter

import pytest

from livetranslator.services.speakers.calibration import calibrate_lag, pair_onsets
from livetranslator.services.speakers.fusion import (
    FusionResult,
    SpeakingInterval,
    add_vote,
    coverage,
    fuse,
)


def iv(user: str, start: float, end: float) -> SpeakingInterval:
    return SpeakingInterval(user, start, end)


# Line under test: 10.0 - 14.0 s (4 s long).


def test_single_discord_speaker_covering_60_percent_wins_and_votes():
    # mika speaks 10.5-13.0 = 2.5 s of 4 s = 62.5 % >= 60 %.
    result = fuse(10.0, 14.0, "0", 0.9, [iv("mika", 10.5, 13.0)], {})
    assert result == FusionResult("discord:mika", ("0", "mika"))


def test_single_speaker_below_60_percent_falls_back_to_largest_overlap_without_vote():
    # 2.0 s of 4 s = 50 %: not decisive, but it is still the only Discord speaker.
    result = fuse(10.0, 14.0, "0", 0.9, [iv("mika", 12.0, 14.0)], {})
    assert result == FusionResult("discord:mika", None)


def test_overlap_resolved_by_the_voice_clusters_votes():
    # Both overlap equally: rin 10-12.5 and mika 11.5-14 (2.5 s each, neither >= 60 % alone
    # as a single speaker). Cluster "1" has voted for mika 3 times, rin once -> mika.
    votes = {"1": Counter({"mika": 3, "rin": 1})}
    intervals = [iv("rin", 10.0, 12.5), iv("mika", 11.5, 14.0)]
    assert fuse(10.0, 14.0, "1", 0.9, intervals, votes) == FusionResult("discord:mika")


def test_overlap_without_useful_votes_takes_the_largest_overlap():
    # rin 10-13 = 3 s, mika 12-14 = 2 s -> rin. Cluster "2" only voted for someone absent.
    votes = {"2": Counter({"sam": 5})}
    intervals = [iv("rin", 10.0, 13.0), iv("mika", 12.0, 14.0)]
    assert fuse(10.0, 14.0, "2", 0.9, intervals, votes) == FusionResult("discord:rin")


def test_no_discord_data_uses_the_voice_label():
    assert fuse(10.0, 14.0, "3", 0.8, [], {}) == FusionResult("voice:3")
    assert fuse(10.0, 14.0, "3", None, [], {}) == FusionResult("voice:3")  # no score given


def test_unreliable_input_is_others():
    assert fuse(10.0, 10.8, "0", 0.9, [iv("mika", 10.0, 10.8)], {}) == FusionResult("others")
    assert fuse(10.0, 14.0, "0", 0.3, [], {}) == FusionResult("others")  # low confidence
    assert fuse(10.0, 14.0, None, None, [], {}) == FusionResult("others")


def test_low_confidence_voice_does_not_vote():
    result = fuse(10.0, 14.0, "0", 0.2, [iv("mika", 10.0, 14.0)], {})
    assert result == FusionResult("discord:mika", None)


def test_coverage_sums_repeated_intervals():
    intervals = [iv("mika", 10.0, 11.0), iv("mika", 12.0, 13.5), iv("rin", 9.0, 10.5)]
    assert coverage(10.0, 14.0, intervals) == {"mika": 2.5, "rin": 0.5}


def test_add_vote_returns_a_new_table():
    votes = {"0": Counter({"mika": 1})}
    updated = add_vote(votes, ("0", "mika"))
    assert updated["0"]["mika"] == 2 and votes["0"]["mika"] == 1
    assert add_vote(votes, None) == {"0": Counter({"mika": 1})}


def test_calibration_median_over_ten_pairs_ignores_outliers():
    # Discord starts every 5 s; VAD onsets 0.3 s later, except two outliers (+1.8, -1.5)
    # and one Discord start with no onset within 2 s (dropped).
    discord = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0]
    vad = [0.3, 5.3, 11.8, 15.3, 18.5, 25.3, 30.3, 35.3, 40.3, 45.3, 50.3, 55.3]
    lags = pair_onsets(discord, vad)
    assert len(lags) == 12  # 60.0 has no onset within 2 s
    # First 10 lags: 0.3, 0.3, 1.8, 0.3, -1.5, 0.3, 0.3, 0.3, 0.3, 0.3 -> sorted median 0.3.
    assert calibrate_lag(discord, vad) == pytest.approx(0.3)


def test_calibration_needs_three_pairs():
    assert calibrate_lag([0.0, 5.0], [0.2, 5.2]) is None
    assert calibrate_lag([0.0, 5.0, 10.0], [0.2, 5.2, 10.4]) == pytest.approx(0.2)
