"""T046 — echo duplicate filter (Tier A, hand-built utterance pairs; D-010)."""

import pytest

from livetranslator.core.chatlog import is_echo, similarity
from livetranslator.core.state import EchoFilterConfig, Source, Utterance

CONFIG = EchoFilterConfig()  # window 4 s, ratio 80 (spec defaults)


def utt(source: Source, text: str, start: float, end: float | None = None, final: bool = True):
    return Utterance(
        id=f"{source}-{start}",
        source=source,
        speaker_id=str(source),
        start=start,
        end=end,
        committed=text,
        is_final=final,
    )


def test_similarity_hand_computed():
    # Indel similarity: "abcd" vs "abcdef" -> 2 insertions over 10 chars -> 1 - 2/10 = 80.0
    assert similarity("abcd", "abcdef") == pytest.approx(80.0)
    assert similarity("Hello, World!", "world hello") == pytest.approx(100.0)


def test_overlapping_and_similar_is_dropped():
    others = utt(Source.OTHERS, "Are you coming to the raid tonight?", 10.0, 12.5)
    me = utt(Source.ME, "are you coming to the raid tonight", 10.3, 12.8)
    assert is_echo(me, [others], CONFIG)


def test_similar_but_six_seconds_apart_is_kept():
    others = utt(Source.OTHERS, "Are you coming to the raid tonight?", 10.0, 12.5)
    me = utt(Source.ME, "are you coming to the raid tonight", 18.5, 20.0)  # 6 s after it ended
    assert not is_echo(me, [others], CONFIG)


def test_overlapping_but_different_is_kept():
    others = utt(Source.OTHERS, "Are you coming to the raid tonight?", 10.0, 12.5)
    me = utt(Source.ME, "yes I'll be there at nine", 11.0, 13.0)
    assert not is_echo(me, [others], CONFIG)


def test_ratio_exactly_at_threshold_is_dropped():
    others = utt(Source.OTHERS, "abcdef", 5.0, 6.0)
    me = utt(Source.ME, "abcd", 5.2, 6.1)  # similarity exactly 80.0 (see hand computation)
    assert is_echo(me, [others], CONFIG)
    assert not is_echo(me, [others], EchoFilterConfig(min_ratio=80.5))


def test_only_final_me_lines_against_others_lines():
    others = utt(Source.OTHERS, "same words here", 1.0, 2.0)
    partial_me = utt(Source.ME, "same words here", 1.0, None, final=False)
    assert not is_echo(partial_me, [others], CONFIG)
    screen = utt(Source.SCREEN, "same words here", 1.0, 2.0)
    me = utt(Source.ME, "same words here", 1.0, 2.0)
    assert not is_echo(me, [screen], CONFIG)
    assert not is_echo(screen, [others], CONFIG)


def test_open_others_line_uses_its_start():
    others = utt(Source.OTHERS, "still talking about the boss fight", 30.0, None, final=False)
    me = utt(Source.ME, "still talking about the boss fight", 31.0, 33.0)
    assert is_echo(me, [others], CONFIG)
