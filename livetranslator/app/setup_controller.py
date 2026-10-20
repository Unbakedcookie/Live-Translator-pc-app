"""First-run setup (T073; spec §5.9): what to download, downloading it, saving the choices.

The wizard pages are presentational; this works out the plan from the choices and the PC:

- Speech: Whisper large-v3-turbo with an NVIDIA card (CUDA), else Whisper small on the
  processor (the same choice the engine makes at start).
- Speaker labels: TitaNet, always (labels from day one, spec §5.13).
- Languages: the packs ticked (each covers that language to and from English).
- Smarter translation (Qwen + its runtime): offered when the card has enough memory.

Downloads run one after another on a worker thread with one progress bar over all of them;
pausing keeps what's done (each file resumes). Only entries not already installed are
fetched, so a PC that already has the models finishes at once.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Signal

from livetranslator.core import actions as a
from livetranslator.core.state import DeviceRef
from livetranslator.core.store import Store
from livetranslator.services.language_packs import LanguagePack, language_packs
from livetranslator.services.models import (
    DownloadCancelled,
    DownloadError,
    ModelEntry,
    ModelManager,
)

SPEECH_GPU = "whisper-large-v3-turbo"
SPEECH_CPU = "whisper-small"
SPEAKERS = "speakers-titanet"
SMART = ("qwen3-4b", "llama-server-vulkan")
GPU_RUNTIME = ("cuda-cublas", "cuda-cudnn", "cuda-nvrtc")  # NVIDIA cards only (D-026)
SMART_MIN_VRAM_MB = 8000  # turbo (~1.2 GB) + Qwen (~2.8 GB) + a game's own needs
COMMON_LANGUAGES = ("es", "zh", "pt", "ru", "de", "fr")  # pre-ticked after your own
PRETICKED = 3

ManagerFactory = Callable[[Path], ModelManager]


@dataclass(frozen=True)
class Machine:
    """What matters about this PC for the plan."""

    cuda: bool
    vram_mb: float | None  # None = unknown (no NVIDIA driver)
    gpu_runtime: bool = True  # NVIDIA's cuBLAS/cuDNN already loadable (pip, or downloaded)

    @property
    def smart_recommended(self) -> bool:
        return self.cuda and (self.vram_mb or 0) >= SMART_MIN_VRAM_MB


@dataclass
class SetupChoices:
    my_language: str = "en"
    mic_languages: tuple[str, ...] = ()
    mic_device: DeviceRef | None = None
    output_device: DeviceRef | None = None
    languages: set[str] = field(default_factory=set)  # language packs to install
    smart: bool = False
    models_dir: Path | None = None


@dataclass(frozen=True)
class SetupPlan:
    entries: tuple[ModelEntry, ...]  # still to download, in order
    free_mb: int

    @property
    def size_mb(self) -> int:
        return sum(e.size_mb for e in self.entries)

    @property
    def fits(self) -> bool:
        return self.size_mb <= self.free_mb


def preticked(my_language: str, available: Sequence[str]) -> set[str]:
    """Your own language plus the most common others that have packs."""
    chosen = {my_language} & set(available)
    for code in COMMON_LANGUAGES:
        if len(chosen - {my_language}) >= PRETICKED:
            break
        if code in available and code != my_language:
            chosen.add(code)
    return chosen


class SetupController(QObject):
    progress = Signal(object, object, str)  # bytes done, total, title (Python ints: > 2 GB)
    finished = Signal(bool, str)  # ok, message for the user

    def __init__(
        self,
        store: Store,
        catalog: Mapping[str, ModelEntry],
        default_models_dir: Path,
        machine: Machine,
        make_manager: ManagerFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._catalog = catalog
        self._default_models_dir = default_models_dir
        self.machine = machine
        self._make_manager = make_manager or (lambda d: ModelManager(d, catalog))
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self.busy = False

    def current_choices(self) -> SetupChoices:
        """Start from the saved settings (setup run again from Settings must not reset
        them)."""
        config = self._store.state.config
        engines = config.engines
        return SetupChoices(
            my_language=config.my_language,
            mic_languages=config.audio.mic_languages,
            mic_device=config.audio.mic_device,
            output_device=config.audio.output_device,
            smart=bool(engines.smart_languages) or engines.smart_fallback,
            models_dir=Path(config.models_dir) if config.models_dir else None,
        )

    # ------------------------------------------------------------ plan

    def models_dir(self, choices: SetupChoices) -> Path:
        return choices.models_dir or self._default_models_dir

    def packs(self, choices: SetupChoices) -> list[LanguagePack]:
        order = [choices.my_language, *COMMON_LANGUAGES]
        return language_packs(self._catalog, self.models_dir(choices), order)

    def wanted(self, choices: SetupChoices) -> list[ModelEntry]:
        ids = [SPEECH_GPU if self.machine.cuda else SPEECH_CPU, SPEAKERS]
        if self.machine.cuda and not self.machine.gpu_runtime:
            ids[1:1] = list(GPU_RUNTIME)  # the built app doesn't ship them
        if choices.smart:
            ids += list(SMART)
        entries = [self._catalog[i] for i in ids if i in self._catalog]
        for pack in self.packs(choices):
            if pack.code in choices.languages:
                entries += list(pack.entries)
        return entries

    def plan(self, choices: SetupChoices) -> SetupPlan:
        manager = self._make_manager(self.models_dir(choices))
        missing = tuple(e for e in self.wanted(choices) if not manager.is_installed(e))
        _needed, free = manager.space_check(list(missing))
        return SetupPlan(missing, free)

    # ------------------------------------------------------------ download

    def download(self, choices: SetupChoices) -> bool:
        """Start downloading what the plan lists. False if already running."""
        if self.busy:
            return False
        plan = self.plan(choices)
        self.busy = True
        self._cancel = threading.Event()
        cancel = self._cancel
        manager = self._make_manager(self.models_dir(choices))
        total = sum(e.size_mb for e in plan.entries) << 20

        def run() -> None:
            base = 0
            ok, message = True, "Everything is downloaded."
            try:
                for entry in plan.entries:
                    start = base

                    def report(done: int, _total: int, start: int = start, e=entry) -> None:
                        self.progress.emit(min(start + done, total), total, e.title)

                    self.progress.emit(min(base, total), total, entry.title)
                    manager.download(entry, report, cancel)
                    base += entry.size_mb << 20
                self.progress.emit(total, total, "")
            except DownloadCancelled:
                ok, message = False, "Paused. Continue whenever you like; nothing is lost."
            except DownloadError as exc:
                ok, message = False, str(exc)
            except Exception as exc:  # report, never crash the wizard
                logger.warning("setup download failed ({})", type(exc).__name__)
                ok, message = False, f"The download failed ({type(exc).__name__})."
            finally:
                self.busy = False
                self.finished.emit(ok, message)

        self._thread = threading.Thread(target=run, name="setup-download", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def wait(self, timeout: float = 30.0) -> None:
        """Tests: wait for the running download to end."""
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------ finish

    def apply(self, choices: SetupChoices) -> None:
        """Save the choices; the app starts speech and opens a window after this."""
        store = self._store
        store.dispatch(a.SetMyLanguage(choices.my_language))
        store.dispatch(
            a.UpdateConfigSection(
                "audio",
                {
                    "mic_languages": choices.mic_languages,
                    "mic_device": choices.mic_device,
                    "output_device": choices.output_device,
                },
            )
        )
        if not choices.smart:
            store.dispatch(
                a.UpdateConfigSection("engines", {"smart_languages": (), "smart_fallback": False})
            )
        if choices.models_dir is not None and choices.models_dir != self._default_models_dir:
            store.dispatch(a.SetModelsDir(str(choices.models_dir)))
        store.dispatch(a.SetWizardCompleted(True))
