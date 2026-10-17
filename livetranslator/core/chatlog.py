"""Chat-log rules (T046; spec §5.2, D-010).

Echo duplicate filter: with speakers (not headphones) the mic hears the other person, so the
same words arrive twice, once as "Others" (loopback) and once as "Me" (mic). A final "Me"
line is treated as an echo when an "Others" line overlapped it in time (within ±window) and
their texts match closely (rapidfuzz token_set_ratio >= min_ratio). Pure functions; the ASR
worker decides what to do with the verdict (T045).
"""

from __future__ import annotations

from collections.abc import Iterable

from rapidfuzz import fuzz, utils

from livetranslator.core.state import EchoFilterConfig, Source, Utterance


def similarity(a: str, b: str) -> float:
    """0-100, word-order insensitive, case and punctuation ignored."""
    return float(fuzz.token_set_ratio(a, b, processor=utils.default_process))


def _overlaps(me: Utterance, other: Utterance, window_s: float) -> bool:
    me_end = me.end if me.end is not None else me.start
    other_end = other.end if other.end is not None else other.start
    return other.start <= me_end + window_s and other_end >= me.start - window_s


def is_echo(me: Utterance, others: Iterable[Utterance], config: EchoFilterConfig) -> bool:
    if me.source is not Source.ME or not me.is_final or not me.text.strip():
        return False
    return any(
        other.source is Source.OTHERS
        and _overlaps(me, other, config.window_s)
        and similarity(me.text, other.text) >= config.min_ratio
        for other in others
    )
