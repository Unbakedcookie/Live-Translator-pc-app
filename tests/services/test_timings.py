"""T091 — rolling percentiles and the timing recorder (Tier A, hand-computed)."""

import threading

import pytest

from livetranslator.services.timings import Timings, percentile, timed


def test_nearest_rank_percentiles():
    assert percentile([], 50) is None
    assert percentile([7.0], 50) == 7.0 and percentile([7.0], 95) == 7.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 50) == 2.0  # rank ceil(0.5·4) = 2
    values = [float(v) for v in range(20, 0, -1)]  # 20..1, unsorted on purpose
    assert percentile(values, 50) == 10.0  # rank 10
    assert percentile(values, 95) == 19.0  # rank ceil(19.0) = 19
    assert percentile([0.1, 0.5, 0.2], 95) == 0.5  # rank ceil(2.85) = 3


def test_window_keeps_the_latest_samples():
    timings = Timings(window=3)
    for v in (1.0, 2.0, 3.0, 4.0):
        timings.record("asr", v)
    assert timings.snapshot("asr") == [2.0, 3.0, 4.0]
    assert timings.snapshot("mt") == []
    timings.clear()
    assert timings.snapshot("asr") == []


def test_timed_records_duration_and_skips_failures():
    ticks = iter([10.0, 10.25, 20.0, 21.0])
    timings = Timings()
    with timed(timings, "mt", clock=lambda: next(ticks)):
        pass
    with pytest.raises(RuntimeError), timed(timings, "mt", clock=lambda: next(ticks)):
        raise RuntimeError("engine failed")
    assert timings.snapshot("mt") == [0.25]
    with timed(None, "mt"):  # no recorder: nothing happens
        pass


def test_record_from_many_threads():
    timings = Timings(window=10_000)

    def work() -> None:
        for _ in range(500):
            timings.record("asr", 0.1)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(timings.snapshot("asr")) == 4000
