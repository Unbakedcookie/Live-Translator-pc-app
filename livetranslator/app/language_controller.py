"""Language Manager actions (T074): download / cancel / remove language packs.

Downloads run one pack at a time on a worker thread with the catalogue's downloader (resume,
cancel, SHA-256 check, safe unzip). Progress and results come back as Qt signals, so the
page only listens. After a pack is added or removed `on_changed` runs on the UI thread (the
app rescans the translation engine's pairs).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from loguru import logger
from PySide6.QtCore import QObject, Signal

from livetranslator.core.languages import DEFAULT_LANGUAGES, language
from livetranslator.core.store import Store
from livetranslator.services.language_packs import (
    LanguagePack,
    language_packs,
    remove_pack,
)
from livetranslator.services.models import (
    DownloadCancelled,
    DownloadError,
    ModelEntry,
    ModelManager,
    Progress,
)


class Downloader(Protocol):
    """What the controller needs from `ModelManager` (tests pass a fake)."""

    def download(
        self, entry: ModelEntry, progress: Progress | None, cancel: threading.Event | None
    ) -> Path: ...


ManagerFactory = Callable[[Path], Downloader]


class LanguageController(QObject):
    progress = Signal(str, object, object)  # code, bytes done (whole pack), total (any size)
    finished = Signal(str, bool, str)  # code, ok, message for the user
    changed = Signal()  # packs added or removed (any thread -> UI thread)

    def __init__(
        self,
        store: Store,
        models_dir: Callable[[], Path],
        catalog: Mapping[str, ModelEntry],
        make_manager: ManagerFactory | None = None,
        on_changed: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._models_dir = models_dir
        self._catalog = catalog
        self._make_manager = make_manager or (lambda d: ModelManager(d, catalog))
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self.busy: str | None = None  # code being downloaded
        if on_changed is not None:
            self.changed.connect(on_changed)

    # ------------------------------------------------------------ reading

    def packs(self) -> list[LanguagePack]:
        order = [lang.code for lang in DEFAULT_LANGUAGES]
        return language_packs(self._catalog, self._models_dir(), order)

    def pack(self, code: str) -> LanguagePack | None:
        return next((p for p in self.packs() if p.code == code), None)

    def in_use(self, code: str) -> list[str]:
        """Why removing `code` would hurt, in plain words (empty = nothing uses it)."""
        config = self._store.state.config
        reasons = []
        if config.my_language == code:
            reasons.append("it's your language")
        windows = [w for w in config.windows if w.target_lang == code]
        if windows:
            count = len(windows)
            reasons.append(f"{count} window{'s' if count > 1 else ''} translate into it")
        return reasons

    # ------------------------------------------------------------ actions

    def install(self, code: str) -> bool:
        """Start downloading `code`'s missing pairs. False if another download is running or
        nothing is missing."""
        pack = self.pack(code)
        if self.busy is not None or pack is None or not pack.missing:
            return False
        self.busy = code
        self._cancel = threading.Event()
        cancel = self._cancel
        entries = pack.missing
        total = sum(e.size_mb for e in entries) << 20

        def run() -> None:
            manager = self._make_manager(self._models_dir())
            base = 0
            ok, message = True, f"{language(code).english} is ready."
            try:
                for entry in entries:
                    start = base

                    def report(done: int, _total: int, start: int = start) -> None:
                        self.progress.emit(code, min(start + done, total), total)

                    manager.download(entry, report, cancel)
                    base += entry.size_mb << 20
                    self.progress.emit(code, min(base, total), total)
            except DownloadCancelled:
                ok, message = False, "Paused. Download again to continue where it stopped."
            except DownloadError as exc:
                ok, message = False, str(exc)
            except Exception as exc:  # report, never crash the page
                logger.warning("language download failed ({})", type(exc).__name__)
                ok, message = False, f"The download failed ({type(exc).__name__})."
            finally:
                self.busy = None
                self.changed.emit()  # some pairs may have landed even if a later one failed
                self.finished.emit(code, ok, message)

        self._thread = threading.Thread(target=run, name=f"language-{code}", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def remove(self, code: str) -> list[str]:
        pack = self.pack(code)
        if pack is None or self.busy == code:
            return []
        removed = remove_pack(pack, self._models_dir())
        if removed:
            self.changed.emit()
        return removed

    def wait(self, timeout: float = 30.0) -> None:
        """Tests: wait for the running download to end."""
        if self._thread is not None:
            self._thread.join(timeout)
