"""Performance metrics for the readout (T091; spec §5.10, §8).

- Durations come from `services/timings.py` (the workers record "asr" and "mt").
- `NvmlSampler`: GPU use and graphics memory via NVML. Any NVML problem (no NVIDIA GPU, old
  driver, a call failing) means "n/a": `sample()` returns None and nothing is raised.
- `MetricsService`: once a second, puts everything into `runtime.metrics` (milliseconds /
  MB / %). A metric that can't be measured is simply absent, which the readout shows as n/a.
  It also measures end-to-end lag: from the end of someone's speech to the moment the
  finished line is on screen with its translations.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger
from PySide6.QtCore import QObject, QTimer

from livetranslator.core import actions as a
from livetranslator.core.state import AppState, Utterance
from livetranslator.core.store import Store
from livetranslator.services.timings import Timings, percentile

SAMPLE_MS = 1000  # spec §5.10: 1 Hz
MB = 1024 * 1024

# runtime.metrics names
GPU_UTIL = "gpu_util_pct"
VRAM_USED = "vram_used_mb"
VRAM_TOTAL = "vram_total_mb"
APP_VRAM = "app_vram_mb"
TIMING_KINDS = ("asr", "mt", "lag")


def metric_name(kind: str, pct: int) -> str:
    return f"{kind}_p{pct}_ms"  # e.g. "asr_p50_ms"


# ---------------------------------------------------------------- GPU (NVML)


@dataclass(frozen=True)
class GpuSample:
    util_pct: float
    vram_used_mb: float
    vram_total_mb: float
    app_vram_mb: float | None  # None: Windows (WDDM) often doesn't report per-process use


class GpuSampler(Protocol):
    def sample(self) -> GpuSample | None: ...

    def close(self) -> None: ...


class NvmlSampler:
    """GPU 0 (the one CUDA uses by default). Every failure → None, logged once."""

    def __init__(self, nvml: Any = None, pid: int | None = None) -> None:
        self._nvml = nvml
        self._pid = os.getpid() if pid is None else pid
        self._handle: Any = None
        self._failed = False

    def _start(self) -> bool:
        if self._handle is not None:
            return True
        if self._failed:
            return False
        try:
            if self._nvml is None:
                import pynvml  # nvidia-ml-py; nvml.dll comes with the NVIDIA driver

                self._nvml = pynvml
            self._nvml.nvmlInit()
            self._handle = self._nvml.nvmlDeviceGetHandleByIndex(0)
        except Exception as exc:  # no driver / no GPU / any NVML error: readout says n/a
            logger.info("GPU readout unavailable ({})", type(exc).__name__)
            self._failed = True
            return False
        return True

    def sample(self) -> GpuSample | None:
        if not self._start():
            return None
        nvml: Any = self._nvml  # pynvml's stubs type struct fields loosely
        try:
            util = nvml.nvmlDeviceGetUtilizationRates(self._handle)
            memory = nvml.nvmlDeviceGetMemoryInfo(self._handle)
        except Exception as exc:  # e.g. the GPU was reset: n/a this second
            logger.debug("NVML sample failed ({})", type(exc).__name__)
            return None
        return GpuSample(
            util_pct=float(util.gpu),
            vram_used_mb=memory.used / MB,
            vram_total_mb=memory.total / MB,
            app_vram_mb=self._app_vram(),
        )

    def _app_vram(self) -> float | None:
        try:
            processes = self._nvml.nvmlDeviceGetComputeRunningProcesses(self._handle)
        except Exception:
            return None
        for process in processes:
            if process.pid == self._pid:
                used = process.usedGpuMemory
                return used / MB if isinstance(used, int) else None
        return None

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception as exc:  # shutting down anyway
                logger.debug("nvmlShutdown failed ({})", type(exc).__name__)
            self._handle = None


# ---------------------------------------------------------------- service


def line_done(utterance: Utterance, targets: set[str]) -> bool:
    """A final line counts as shown once every needed translation is current."""
    if not utterance.is_final or utterance.end is None:
        return False
    needed = {t for t in targets if t != utterance.language}
    return all(utterance.translated_from.get(t) == utterance.text for t in needed)


TargetsFn = Callable[[Utterance, AppState], set[str]]


class MetricsService(QObject):
    def __init__(
        self,
        store: Store,
        timings: Timings,
        gpu: GpuSampler,
        targets: TargetsFn,
        clock: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self.timings = timings
        self._gpu = gpu
        self._targets = targets
        self._clock = clock
        self._lag_done: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(SAMPLE_MS)
        self._timer.timeout.connect(self.tick)
        store.utterance_updated.connect(self._on_utterance)
        store.session_cleared.connect(self._lag_done.clear)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._gpu.close()

    def _on_utterance(self, utterance_id: str) -> None:
        if utterance_id in self._lag_done:
            return
        state = self._store.state
        utterance = state.session.utterance(utterance_id)
        if utterance is None or utterance.end is None:
            return
        if line_done(utterance, self._targets(utterance, state)):
            self._lag_done.add(utterance_id)
            self.timings.record("lag", max(0.0, self._clock() - utterance.end))

    def tick(self) -> None:
        values: dict[str, float] = {}
        gpu = self._gpu.sample()
        if gpu is not None:
            values[GPU_UTIL] = gpu.util_pct
            values[VRAM_USED] = round(gpu.vram_used_mb)
            values[VRAM_TOTAL] = round(gpu.vram_total_mb)
            if gpu.app_vram_mb is not None:
                values[APP_VRAM] = round(gpu.app_vram_mb)
        for kind in TIMING_KINDS:
            samples = self.timings.snapshot(kind)
            for pct in (50, 95):
                value = percentile(samples, pct)
                if value is not None:
                    values[metric_name(kind, pct)] = round(value * 1000)
        if values:
            self._store.dispatch(
                a.Batch(tuple(a.SetMetric(name, value) for name, value in values.items()))
            )
