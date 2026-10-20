"""T073 — first-run plan, downloads and saved choices (fake downloader, real catalogue rules)."""

import threading
from pathlib import Path

from livetranslator.app.setup_controller import (
    SPEAKERS,
    SPEECH_CPU,
    SPEECH_GPU,
    Machine,
    SetupChoices,
    SetupController,
    preticked,
)
from livetranslator.core.state import AppState, DeviceRef
from livetranslator.core.store import Store
from livetranslator.services.models import (
    DownloadCancelled,
    DownloadError,
    ModelEntry,
    UrlSource,
)

SHA = "0" * 64


def entry(entry_id: str, dest: str, size: int = 2, kind: str = "speech") -> ModelEntry:
    return ModelEntry(
        id=entry_id,
        title=entry_id,
        kind=kind,
        license="MIT",
        size_mb=size,
        source=UrlSource(f"https://example.test/{entry_id}", SHA),
        dest=dest,
        marker="model.bin",
    )


CATALOG = {
    e.id: e
    for e in (
        entry(SPEECH_GPU, "whisper/large-v3-turbo", 1547),
        entry(SPEECH_CPU, "whisper/small", 464),
        entry(SPEAKERS, "speakers", 97, "speakers"),
        entry("qwen3-4b", "qwen3-4b", 2382, "translation"),
        entry("llama-server-vulkan", "llama.cpp/vulkan", 31, "runtime"),
        entry("opus-mt-es-en", "opus-mt/es-en", 150, "translation"),
        entry("opus-mt-en-es", "opus-mt/en-es", 150, "translation"),
        entry("opus-mt-ja-en", "opus-mt/ja-en", 150, "translation"),
        entry("cuda-cublas", "cuda/cublas", 528, "gpu-runtime"),
        entry("cuda-cudnn", "cuda/cudnn", 709, "gpu-runtime"),
        entry("cuda-nvrtc", "cuda/nvrtc", 73, "gpu-runtime"),
    )
}


class FakeManager:
    def __init__(self, models: Path, fail: str = "", block: bool = False) -> None:
        self.models, self.fail, self.block = models, fail, block
        self.started = threading.Event()

    def is_installed(self, e: ModelEntry) -> bool:
        return (self.models / e.dest / e.marker).exists()

    def space_check(self, entries) -> tuple[int, int]:
        return sum(e.size_mb for e in entries), 10_000

    def download(self, e: ModelEntry, progress, cancel) -> Path:
        self.started.set()
        if self.block:
            while not cancel.is_set():
                cancel.wait(0.01)
            raise DownloadCancelled("paused")
        if e.id == self.fail:
            raise DownloadError("Couldn't connect. Check the internet connection.")
        progress((e.size_mb << 20) // 2, e.size_mb << 20)
        folder = self.models / e.dest
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.bin").write_bytes(b"x")
        return folder


GPU_PC = Machine(cuda=True, vram_mb=12288)


def make(tmp_path: Path, machine: Machine = GPU_PC, manager=None):
    store = Store(AppState())
    fake = manager or FakeManager(tmp_path / "models")
    ctl = SetupController(store, CATALOG, tmp_path / "models", machine, lambda _d: fake)  # type: ignore[arg-type,return-value]
    return store, ctl, fake


def test_the_plan_fits_the_pc(tmp_path: Path):
    _, gpu, _ = make(tmp_path)
    ids = [e.id for e in gpu.plan(SetupChoices(languages={"es"}, smart=True)).entries]
    assert ids == [
        SPEECH_GPU,
        SPEAKERS,
        "qwen3-4b",
        "llama-server-vulkan",
        "opus-mt-es-en",
        "opus-mt-en-es",
    ]
    _, cpu, _ = make(tmp_path, Machine(cuda=False, vram_mb=None))
    plan = cpu.plan(SetupChoices())
    assert [e.id for e in plan.entries] == [SPEECH_CPU, SPEAKERS]
    assert plan.size_mb == 561 and plan.fits
    assert Machine(cuda=True, vram_mb=12288).smart_recommended
    assert not Machine(cuda=True, vram_mb=6144).smart_recommended


def test_preticked_languages():
    assert preticked("en", ["es", "zh", "ja", "pt", "ru"]) == {"es", "zh", "pt"}
    assert preticked("ja", ["es", "zh", "ja", "pt"]) == {"ja", "es", "zh", "pt"}
    assert preticked("en", ["ja"]) == set()


def test_download_shows_one_bar_and_skips_what_is_installed(qtbot, tmp_path: Path):
    _, ctl, _ = make(tmp_path)
    folder = tmp_path / "models" / "speakers"
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"x")  # already there: not fetched again
    events: list[tuple] = []
    ctl.progress.connect(lambda done, total, title: events.append(("p", done, total, title)))
    ctl.finished.connect(lambda ok, msg: events.append(("f", ok, msg)))
    assert ctl.download(SetupChoices())
    qtbot.waitUntil(lambda: any(e[0] == "f" for e in events), timeout=5000)
    total = 1547 << 20
    progress = [e for e in events if e[0] == "p"]
    assert all(e[2] == total for e in progress) and progress[-1][1] == total
    assert events[-1] == ("f", True, "Everything is downloaded.")
    assert ctl.plan(SetupChoices()).entries == ()  # nothing left


def test_pause_and_errors_are_reported(qtbot, tmp_path: Path):
    blocking = FakeManager(tmp_path / "models", block=True)
    _, ctl, _ = make(tmp_path, manager=blocking)
    done: list[tuple[bool, str]] = []
    ctl.finished.connect(lambda ok, msg: done.append((ok, msg)))
    ctl.download(SetupChoices())
    assert blocking.started.wait(5)
    assert not ctl.download(SetupChoices())  # one at a time
    ctl.cancel()
    qtbot.waitUntil(lambda: bool(done), timeout=5000)
    assert done[0][0] is False and "Paused" in done[0][1]
    failing = FakeManager(tmp_path / "other", fail=SPEECH_GPU)
    _, ctl2, _ = make(tmp_path, manager=failing)
    done.clear()
    ctl2.finished.connect(lambda ok, msg: done.append((ok, msg)))
    ctl2.download(SetupChoices())
    qtbot.waitUntil(lambda: bool(done), timeout=5000)
    assert done == [(False, "Couldn't connect. Check the internet connection.")]


def test_finishing_saves_the_choices(tmp_path: Path):
    store, ctl, _ = make(tmp_path)
    mic = DeviceRef(name="Headset Mic")
    ctl.apply(
        SetupChoices(
            my_language="de",
            mic_languages=("es", "de"),
            mic_device=mic,
            smart=False,
            models_dir=tmp_path / "elsewhere",
        )
    )
    config = store.state.config
    assert config.my_language == "de" and config.wizard_completed
    assert config.audio.mic_languages == ("es", "de") and config.audio.mic_device == mic
    assert config.engines.smart_languages == () and not config.engines.smart_fallback
    assert config.models_dir == str(tmp_path / "elsewhere")


def test_nvidia_libraries_come_with_the_plan_only_when_missing(tmp_path: Path):
    """D-026: the built app doesn't ship cuBLAS/cuDNN; NVIDIA cards download them."""
    _, built, _ = make(tmp_path, Machine(cuda=True, vram_mb=12288, gpu_runtime=False))
    ids = [e.id for e in built.plan(SetupChoices()).entries]
    assert ids == [SPEECH_GPU, "cuda-cublas", "cuda-cudnn", "cuda-nvrtc", SPEAKERS]
    _, dev, _ = make(tmp_path, Machine(cuda=True, vram_mb=12288, gpu_runtime=True))
    assert "cuda-cudnn" not in [e.id for e in dev.plan(SetupChoices()).entries]
    _, cpu, _ = make(tmp_path, Machine(cuda=False, vram_mb=None, gpu_runtime=False))
    assert "cuda-cublas" not in [e.id for e in cpu.plan(SetupChoices()).entries]
