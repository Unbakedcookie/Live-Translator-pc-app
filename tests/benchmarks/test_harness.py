"""T031 — benchmark harness (Tier A) + a live NVML read on the user's GPU."""

import itertools
import sys
from pathlib import Path

import pytest

from benchmarks import harness
from benchmarks.harness import VramMonitor, gpu_info, markdown_table, time_calls, write_results


def test_time_calls_skips_warmup_and_uses_clock():
    calls: list[int] = []
    ticks = itertools.count(0.0, 0.25)  # each clock() call advances 250 ms
    results, stats = time_calls(
        lambda: calls.append(1) or len(calls), repeats=3, warmup=2, clock=lambda: next(ticks)
    )
    assert len(calls) == 5  # 2 warm-up + 3 measured
    assert results == [3, 4, 5]
    assert (stats.n, stats.p50_ms, stats.p95_ms) == (3, 250.0, 250.0)


def test_markdown_table_formatting():
    table = markdown_table(
        ["Engine", "WER", "p50 ms", "VRAM MB"], [["turbo", 0.0712, 412.34, None]]
    )
    assert table == (
        "| Engine | WER | p50 ms | VRAM MB |\n|---|---|---|---|\n| turbo | 0.0712 | 412.3 | n/a |\n"
    )


def test_write_results(tmp_path: Path):
    out = tmp_path / "r" / "asr.md"
    write_results(out, "ASR", [("Setup", "RTX 3060\n"), ("Results", "| a |\n")])
    assert (
        out.read_text(encoding="utf-8") == "# ASR\n\n## Setup\n\nRTX 3060\n\n## Results\n\n| a |\n"
    )


def test_vram_monitor_without_nvml(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(harness, "_nvml", lambda: None)
    with VramMonitor() as vram:
        pass
    assert vram.peak_delta_mb is None
    assert gpu_info() is None


@pytest.mark.skipif(sys.platform != "win32", reason="the user's RTX 3060")
def test_live_gpu_read():
    info = gpu_info()
    if info is None:
        pytest.skip("NVML not available")
    assert "3060" in info.name
    assert 11_000 < info.total_mb < 13_000
    with VramMonitor(interval_s=0.01) as vram:
        pass
    assert vram.peak_delta_mb is not None and vram.peak_delta_mb >= 0
