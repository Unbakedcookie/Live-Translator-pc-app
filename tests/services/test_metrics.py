"""T091 — GPU sampling via (fake) NVML and the 1 Hz metrics service."""

from types import SimpleNamespace

import pytest

from livetranslator.core import actions as a
from livetranslator.core.state import AppState, Source, Utterance
from livetranslator.core.store import Store
from livetranslator.services.metrics import (
    APP_VRAM,
    GPU_UTIL,
    VRAM_TOTAL,
    VRAM_USED,
    GpuSample,
    MetricsService,
    NvmlSampler,
    line_done,
)
from livetranslator.services.timings import Timings

MB = 1024 * 1024


class FakeNvml:
    def __init__(self, fail_init=False, fail_sample=False, used_by_app: object = 300 * MB):
        self.fail_init = fail_init
        self.fail_sample = fail_sample
        self.used_by_app = used_by_app
        self.inits = 0
        self.shutdowns = 0

    def nvmlInit(self):
        self.inits += 1
        if self.fail_init:
            raise OSError("NVML Shared Library Not Found")

    def nvmlDeviceGetHandleByIndex(self, index):
        return ("gpu", index)

    def nvmlDeviceGetUtilizationRates(self, handle):
        if self.fail_sample:
            raise RuntimeError("GPU is lost")
        return SimpleNamespace(gpu=37, memory=12)

    def nvmlDeviceGetMemoryInfo(self, handle):
        return SimpleNamespace(used=4096 * MB, total=12288 * MB, free=8192 * MB)

    def nvmlDeviceGetComputeRunningProcesses(self, handle):
        return [
            SimpleNamespace(pid=1, usedGpuMemory=999 * MB),
            SimpleNamespace(pid=42, usedGpuMemory=self.used_by_app),
        ]

    def nvmlShutdown(self):
        self.shutdowns += 1


def test_sample_reads_utilisation_and_memory():
    nvml = FakeNvml()
    sampler = NvmlSampler(nvml, pid=42)
    assert sampler.sample() == GpuSample(37.0, 4096.0, 12288.0, 300.0)
    sampler.sample()
    assert nvml.inits == 1  # initialised once
    sampler.close()
    assert nvml.shutdowns == 1


def test_windows_without_per_process_memory():
    sample = NvmlSampler(FakeNvml(used_by_app=None), pid=42).sample()
    assert sample is not None and sample.app_vram_mb is None
    other = NvmlSampler(FakeNvml(), pid=7).sample()  # our process isn't using the GPU
    assert other is not None and other.app_vram_mb is None


def test_no_nvml_means_n_a_without_errors():
    nvml = FakeNvml(fail_init=True)
    sampler = NvmlSampler(nvml, pid=42)
    assert sampler.sample() is None and sampler.sample() is None
    assert nvml.inits == 1  # gave up after the first failure
    sampler.close()
    assert nvml.shutdowns == 0
    assert NvmlSampler(FakeNvml(fail_sample=True), pid=42).sample() is None


class FakeGpu:
    def __init__(self, sample: GpuSample | None) -> None:
        self.value = sample
        self.closed = False

    def sample(self) -> GpuSample | None:
        return self.value

    def close(self) -> None:
        self.closed = True


def make(gpu: GpuSample | None, now: list[float]):
    store = Store(AppState())
    timings = Timings()
    service = MetricsService(
        store, timings, FakeGpu(gpu), lambda u, s: {"en", "ja"}, clock=lambda: now[0]
    )
    return store, timings, service


def test_tick_puts_rounded_values_into_the_store(qtbot):
    store, timings, service = make(GpuSample(37.0, 4096.4, 12288.0, 300.6), [0.0])
    for seconds in (0.30, 0.10, 0.20, 0.40):
        timings.record("asr", seconds)
    timings.record("mt", 0.116)
    service.tick()
    metrics = store.state.runtime.metrics
    assert metrics[GPU_UTIL] == 37.0
    assert (metrics[VRAM_USED], metrics[VRAM_TOTAL], metrics[APP_VRAM]) == (4096, 12288, 301)
    assert metrics["asr_p50_ms"] == 200  # sorted .1 .2 .3 .4, rank 2
    assert metrics["asr_p95_ms"] == 400  # rank ceil(3.8) = 4
    assert metrics["mt_p50_ms"] == 116 and metrics["mt_p95_ms"] == 116
    assert "lag_p50_ms" not in metrics  # nothing measured yet: absent = n/a


def test_without_a_gpu_only_timings_are_reported(qtbot):
    store, timings, service = make(None, [0.0])
    service.tick()
    assert store.state.runtime.metrics == {}
    timings.record("asr", 0.5)
    service.tick()
    assert set(store.state.runtime.metrics) == {"asr_p50_ms", "asr_p95_ms"}
    service.stop()


def utterance(**fields) -> Utterance:
    base: dict[str, object] = {
        "id": "u1",
        "source": Source.OTHERS,
        "speaker_id": "voice:0",
        "start": 10.0,
        "committed": "hola",
        "language": "es",
    }
    base.update(fields)
    return Utterance.model_validate(base)


def test_line_done_needs_final_and_every_current_translation():
    targets = {"en", "ja", "es"}  # "es" is the line's own language: nothing to translate
    assert not line_done(utterance(), targets)
    final = utterance(is_final=True, end=12.0)
    assert not line_done(final, targets)
    partly = final.model_copy(
        update={"translations": {"en": "hi"}, "translated_from": {"en": "hola"}}
    )
    assert not line_done(partly, targets)
    stale = partly.model_copy(
        update={
            "translations": {"en": "hi", "ja": "x"},
            "translated_from": {"en": "hola", "ja": "hol"},
        }
    )
    assert not line_done(stale, targets)
    done = stale.model_copy(update={"translated_from": {"en": "hola", "ja": "hola"}})
    assert line_done(done, targets)


def test_lag_is_measured_once_from_speech_end(qtbot):
    now = [0.0]
    store, timings, _ = make(None, now)
    store.dispatch(a.AddUtterance(utterance()))
    store.dispatch(a.UpdateUtterance("u1", {"is_final": True, "end": 12.0}))
    now[0] = 12.4
    store.dispatch(a.SetTranslation("u1", "en", "hi", "hola"))
    assert timings.snapshot("lag") == []  # Japanese still missing
    now[0] = 12.9
    store.dispatch(a.SetTranslation("u1", "ja", "やあ", "hola"))
    now[0] = 30.0
    store.dispatch(a.SetTranslation("u1", "ja", "やあ!", "hola"))  # later edits don't count
    assert timings.snapshot("lag") == [pytest.approx(0.9)]
