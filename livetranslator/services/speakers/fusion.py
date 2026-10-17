"""Speaker fusion: Discord speaking events + voice clusters -> one label per line (T101;
spec §5.13 "Fusion"). Pure functions; the caller keeps the state (vote table) and passes it in.

For a final "Others" line [t0, t1]:
1. Discord events are already shifted by the calibrated lag (calibration.py).
2. Exactly one Discord user covers >= 60 % of the line -> that user. The voice cluster heard
   in the line gets one vote for that user (so later lines can be resolved by voice).
3. Several Discord users overlap -> the user the line's voice cluster has most votes for,
   if that user is among them; otherwise the user with the largest overlap.
4. No Discord data -> the voice cluster ("voice:<n>"; its session rename is applied by the UI).
5. Nothing reliable (line < 1 s, or a low-confidence cluster) -> "others".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SINGLE_COVER = 0.6  # share of the line one Discord speaker must cover alone
MIN_LINE_S = 1.0
MIN_CONFIDENCE = 0.5
OTHERS = "others"

Votes = Mapping[str, Counter[str]]  # voice cluster id -> Discord user id -> votes


@dataclass(frozen=True)
class SpeakingInterval:
    user_id: str
    start: float
    end: float  # an open interval (still speaking) is passed with end = now


@dataclass(frozen=True)
class FusionResult:
    speaker_id: str  # "discord:<user id>", "voice:<n>" or "others"
    vote: tuple[str, str] | None = None  # (voice cluster, Discord user) to count


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def coverage(start: float, end: float, intervals: Sequence[SpeakingInterval]) -> dict[str, float]:
    """Seconds of [start, end] covered by each Discord user (intervals may repeat users)."""
    covered: dict[str, float] = {}
    for interval in intervals:
        shared = _overlap(start, end, interval.start, interval.end)
        if shared > 0:
            covered[interval.user_id] = covered.get(interval.user_id, 0.0) + shared
    return covered


def fuse(
    start: float,
    end: float,
    voice_cluster: str | None,
    confidence: float | None,
    intervals: Sequence[SpeakingInterval],
    votes: Votes,
) -> FusionResult:
    duration = end - start
    reliable_voice = voice_cluster is not None and (
        confidence is None or confidence >= MIN_CONFIDENCE
    )
    if duration < MIN_LINE_S:
        return FusionResult(OTHERS)
    covered = coverage(start, end, intervals)
    if covered:
        if len(covered) == 1:
            user, seconds = next(iter(covered.items()))
            if seconds / duration >= SINGLE_COVER:
                vote = (voice_cluster, user) if reliable_voice and voice_cluster else None
                return FusionResult(f"discord:{user}", vote)
        if reliable_voice and voice_cluster is not None and voice_cluster in votes:
            ranked = votes[voice_cluster].most_common()
            for user, _count in ranked:
                if user in covered:
                    return FusionResult(f"discord:{user}")
        user = max(covered, key=lambda u: (covered[u], u))
        return FusionResult(f"discord:{user}")
    if reliable_voice and voice_cluster is not None:
        return FusionResult(f"voice:{voice_cluster}")
    return FusionResult(OTHERS)


def add_vote(votes: Votes, vote: tuple[str, str] | None) -> dict[str, Counter[str]]:
    """A new vote table with `vote` counted (the input is not modified)."""
    table = {cluster: Counter(users) for cluster, users in votes.items()}
    if vote is not None:
        cluster, user = vote
        table.setdefault(cluster, Counter())[user] += 1
    return table
