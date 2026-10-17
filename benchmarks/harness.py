"""Benchmark harness: call timing, GPU memory sampling, markdown results (T031; spec §8).

VRAM is sampled from NVML as device-wide used memory (per-process numbers aren't available
under Windows WDDM), so run benchmarks with games and other GPU apps closed. The delta over
the baseline taken at the start is what an engine adds.
"""

from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from benchmarks.metrics import LatencyStats

MB = 1024 * 1024


def _nvml() -> Any | None:
    try:
        nvml: Any = importlib.import_module("pynvml")
        nvml.nvmlInit()
    except Exception:
        return None
    return nvml


@dataclass(frozen=True)
class GpuInfo:
    name: str
    driver: str
    total_mb: int


def gpu_info() -> GpuInfo | None:
    nvml = _nvml()
    if nvml is None:
        return None
    handle = nvml.nvmlDeviceGetHandleByIndex(0)
    name = nvml.nvmlDeviceGetName(handle)
    driver = nvml.nvmlSystemGetDriverVersion()
    total = nvml.nvmlDeviceGetMemoryInfo(handle).total
    return GpuInfo(str(name), str(driver), int(total // MB))


class VramMonitor:
    """`with VramMonitor() as vram: ...` then read `vram.peak_delta_mb` (None without NVML)."""

    def __init__(self, interval_s: float = 0.05) -> None:
        self._interval = interval_s
        self._nvml = _nvml()
        self._handle: Any = None
        self.baseline_mb: int | None = None
        self.peak_mb: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _used_mb(self) -> int:
        assert self._nvml is not None  # nosec B101 - guarded by callers
        return int(self._nvml.nvmlDeviceGetMemoryInfo(self._handle).used // MB)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            used = self._used_mb()
            if self.peak_mb is None or used > self.peak_mb:
                self.peak_mb = used

    def __enter__(self) -> VramMonitor:
        if self._nvml is not None:
            self._handle = self._nvml.nvmlDeviceGetHandleByIndex(0)
            self.baseline_mb = self.peak_mb = self._used_mb()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join()
            used = self._used_mb()
            if self.peak_mb is None or used > self.peak_mb:
                self.peak_mb = used

    @property
    def peak_delta_mb(self) -> int | None:
        if self.baseline_mb is None or self.peak_mb is None:
            return None
        return self.peak_mb - self.baseline_mb


def time_calls[T](
    fn: Callable[[], T],
    repeats: int,
    warmup: int = 1,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[list[T], LatencyStats]:
    """Call `fn` warmup + repeats times; time only the measured calls."""
    for _ in range(warmup):
        fn()
    results: list[T] = []
    samples: list[float] = []
    for _ in range(repeats):
        start = clock()
        results.append(fn())
        samples.append(clock() - start)
    return results, LatencyStats.from_seconds(samples)


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def cell(value: object) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.3g}" if abs(value) < 10 else f"{value:.1f}"
        return str(value)

    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows),
    ]
    return "\n".join(lines) + "\n"


def write_results(path: Path, title: str, sections: Sequence[tuple[str, str]]) -> None:
    """Write `# title` then `## heading` + body for each section."""
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [f"# {title}\n"]
    for heading, body in sections:
        parts.append(f"\n## {heading}\n\n{body}")
    path.write_text("".join(parts), encoding="utf-8")
