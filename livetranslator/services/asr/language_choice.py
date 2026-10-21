"""Which language another person's line is in (Settings "Others speak", 2026-10-20).

- Detect any language: the likeliest of the languages the app can translate (SUPPORTED).
  Whisper knows ~99; a line taken for one we can't translate (the user's log: noisy lines
  as Icelandic) was useless, so detection stays among ours.
- Listed languages only: the likeliest of those (one = always that one).
- Listed + "Anything else": among SUPPORTED, but a listed language wins whenever it scores at
  least PREFER_RATIO of the top language (D-044). Measured on 160 FLEURS clips in 8 languages,
  each language in turn as the listed one: the listed language recognised after 1 s of speech
  63 % -> 92 % (1.5 s: 73 -> 92 %); other languages taken for it at 1 s 4 -> 28 %
  (1.5 s: 3 -> 18 %); whole lines right 100 % either way (each line is checked again at the
  end, and a preferred pick never counts as sure, so partials keep re-checking).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from livetranslator.core.languages import DEFAULT_LANGUAGES, OTHER_LANGUAGES

SUPPORTED: tuple[str, ...] = tuple(lang.code for lang in (*DEFAULT_LANGUAGES, *OTHER_LANGUAGES))
PREFER_RATIO = 0.1  # D-044


def others_candidates(
    listed: Sequence[str], anything_else: bool
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(candidates to choose among, preferred ones) for the "Others speak" setting."""
    if not listed:
        return SUPPORTED, ()
    if anything_else:
        extra = tuple(code for code in SUPPORTED if code not in listed)
        return (*listed, *extra), tuple(listed)
    return tuple(listed), ()


def choose(scores: Mapping[str, float], preferred: Sequence[str]) -> str:
    """The language for a line from candidate scores (shares summing to 1)."""
    best = max(scores, key=lambda code: scores[code])
    if not preferred or best in preferred:
        return best
    pick = max(preferred, key=lambda code: scores.get(code, 0.0))
    return pick if scores.get(pick, 0.0) >= PREFER_RATIO * scores[best] else best
