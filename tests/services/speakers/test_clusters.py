"""T102 — online voice clusters with hand-made 2-D fingerprints (Tier A).

Unit vectors at angle θ: cosine similarity between angles a and b is cos(a - b).
cos 30° = 0.866, cos 60° = 0.5, cos 90° = 0. Threshold 0.55 sits between 30° and 60°.
"""

import math

import numpy as np

from livetranslator.services.speakers.clusters import VoiceClusters


def at(degrees: float) -> np.ndarray:
    r = math.radians(degrees)
    return np.array([math.cos(r), math.sin(r)], dtype=np.float32)


def test_close_voices_join_far_voices_start_new_speakers():
    clusters = VoiceClusters(threshold=0.55)
    first = clusters.assign(at(0))
    assert first.cluster == "0" and first.created and first.similarity is None
    same = clusters.assign(at(30))  # cos 30° = 0.866 >= 0.55
    assert same.cluster == "0" and abs((same.similarity or 0) - 0.866) < 0.001
    other = clusters.assign(at(90))  # vs centroid ~15°: cos 75° = 0.259 < 0.55
    assert other.cluster == "1" and other.created
    assert clusters.count == 2


def test_peek_never_learns_or_creates():
    clusters = VoiceClusters(threshold=0.55)
    assert clusters.peek(at(0)).cluster is None  # nobody known yet
    clusters.assign(at(0))
    assert clusters.peek(at(20)).cluster == "0"
    assert clusters.peek(at(80)).cluster is None  # cos 80° = 0.17
    assert clusters.count == 1


def test_running_mean_is_weighted_by_duration():
    clusters = VoiceClusters(threshold=0.55)
    clusters.assign(at(0), weight=9.0)  # long line at 0°
    clusters.assign(at(50), weight=1.0)  # short line at 50° joins (cos 50° = 0.64)
    # Centroid = 9·(1, 0) + (0.643, 0.766) -> atan(0.766 / 9.643) = 4.5°. A voice at 70° is
    # cos(65.5°) = 0.41 < 0.55 away -> a new speaker. Unweighted, the centroid would sit at
    # 25° and 70° would join (cos 45° = 0.71), so this checks the weighting.
    assert clusters.assign(at(70)).created


def test_max_speakers_forces_the_closest_match():
    clusters = VoiceClusters(threshold=0.99, max_speakers=2)
    clusters.assign(at(0))
    clusters.assign(at(90))
    third = clusters.assign(at(80))  # no match at 0.99, but the limit is reached
    assert third.cluster == "1" and not third.created
    assert clusters.count == 2


def test_reset_forgets_every_voice():
    clusters = VoiceClusters()
    clusters.assign(at(0))
    clusters.reset()
    assert clusters.count == 0
    assert clusters.assign(at(0)).created
