"""LocalAgreement-n streaming policy (T044; spec §5.4). Own implementation of the approach
from whisper_streaming (Macháček et al., MIT).

While someone is speaking, the ASR re-decodes the growing utterance buffer every update
interval. A word becomes *committed* (stable, shown in the primary colour) once the last `n`
hypotheses agree on it at the same position after the already committed words. Everything
after that is *tentative* (may still change, shown in the secondary colour). Committed words
are never revoked; at the end of the utterance `finalize` commits the final decode.

Words are compared after normalisation (case, punctuation, width), so "Hello," vs "hello"
agree. Hypotheses always cover the utterance from its start, so the already-committed part is
skipped by timestamp: only words starting at or after the last committed word's end count.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

OVERLAP_TOLERANCE_S = 0.08  # Whisper word timestamps jitter by a few tens of ms


class TimedWord(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def start(self) -> float: ...

    @property
    def end(self) -> float: ...


@dataclass(frozen=True)
class AgreementState:
    committed: str  # all committed text of the utterance so far
    tentative: str  # current guess for the rest
    newly_committed: str  # what this update added (for incremental consumers)


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if not ch.isspace() and unicodedata.category(ch)[0] != "P")


def join_words(words: Sequence[TimedWord]) -> str:
    """Whisper words carry their own leading spaces (none for CJK), so plain concatenation
    gives correct spacing for every script."""
    return "".join(w.text for w in words).strip()


class LocalAgreement:
    def __init__(self, n: int = 2) -> None:
        if n < 2:
            raise ValueError("LocalAgreement needs n >= 2")
        self._n = n
        self._committed: list[TimedWord] = []
        self._previous_tails: list[list[TimedWord]] = []

    @property
    def committed_text(self) -> str:
        return join_words(self._committed)

    def _tail(self, words: Sequence[TimedWord]) -> list[TimedWord]:
        if not self._committed:
            return [w for w in words if _norm(w.text)]
        boundary = self._committed[-1].end - OVERLAP_TOLERANCE_S
        tail = [w for w in words if w.start >= boundary and _norm(w.text)]
        return tail[self._repeated_prefix(tail) :]

    def _repeated_prefix(self, tail: Sequence[TimedWord]) -> int:
        """How many leading tail words are the last committed words again, re-timed.

        The tolerance above lets a committed word whose timestamp shifted by a few tens of ms
        back into the tail ("cornered the the inmates", T045 integration run). A repeat
        counts only when it overlaps the committed word in time; a real spoken repetition
        ("very very") starts after it ended.
        """
        for k in range(min(3, len(tail), len(self._committed)), 0, -1):
            committed = self._committed[-k:]
            if [_norm(w.text) for w in tail[:k]] == [_norm(w.text) for w in committed] and (
                tail[0].start < committed[0].end + OVERLAP_TOLERANCE_S
            ):
                return k
        return 0

    def update(self, words: Sequence[TimedWord]) -> AgreementState:
        """Feed the latest hypothesis for the whole utterance buffer."""
        tail = self._tail(words)
        history = [*self._previous_tails[-(self._n - 1) :], tail]
        agreed = 0
        if len(history) == self._n:
            for i in range(min(len(t) for t in history)):
                if len({_norm(t[i].text) for t in history}) != 1:
                    break
                agreed = i + 1
        newly = tail[:agreed]
        self._committed.extend(newly)
        remaining = tail[agreed:]
        # Every kept tail is re-based past the words just committed, so the next comparison
        # lines up position by position; keep the newest n-1 (fewer while warming up).
        self._previous_tails = [t[agreed:] for t in history][-(self._n - 1) :]
        return AgreementState(self.committed_text, join_words(remaining), join_words(newly))

    def finalize(self, words: Sequence[TimedWord]) -> AgreementState:
        """End of utterance: commit everything the final decode has after the committed part."""
        rest = self._tail(words)
        self._committed.extend(rest)
        self._previous_tails = []
        return AgreementState(self.committed_text, "", join_words(rest))

    def reset(self) -> None:
        self._committed = []
        self._previous_tails = []
