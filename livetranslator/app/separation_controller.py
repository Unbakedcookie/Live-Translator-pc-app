"""Settings → Speakers "Separate people talking over each other" (experimental, 2026-10-20):
turning it on downloads the two small models it needs, then switches it on.

The models (services/speakers/separation.py) are a catalogue download like any other: the
overlap detector from k2-fsa's Hugging Face mirror, the separation model from the app's own
model repo (`tools.model_hosting extras`). Until that repo has it, the switch says so.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from loguru import logger
from PySide6.QtCore import QObject, Signal

from livetranslator.core import actions as a
from livetranslator.core.store import Store
from livetranslator.services.models import (
    DownloadCancelled,
    DownloadError,
    ModelEntry,
    ModelManager,
    Progress,
)
from livetranslator.services.speakers.separation import MODEL_IDS, installed


class Downloader(Protocol):
    def is_installed(self, entry: ModelEntry) -> bool: ...

    def download(
        self, entry: ModelEntry, progress: Progress | None, cancel: threading.Event | None
    ) -> Path: ...


ManagerFactory = Callable[[Path], Downloader]


class SeparationController(QObject):
    progress = Signal(object, object)  # bytes done, total
    finished = Signal(bool, str)  # ok, message for the user

    def __init__(
        self,
        store: Store,
        models_dir: Callable[[], Path],
        catalog: Mapping[str, ModelEntry],
        make_manager: ManagerFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._models_dir = models_dir
        self._catalog = catalog
        self._make_manager = make_manager or (lambda d: ModelManager(d, catalog))
        self._thread: threading.Thread | None = None
        self.busy = False

    @property
    def installed(self) -> bool:
        return installed(self._models_dir())

    def missing(self) -> list[ModelEntry]:
        manager = self._make_manager(self._models_dir())
        return [
            self._catalog[i]
            for i in MODEL_IDS
            if i in self._catalog and not manager.is_installed(self._catalog[i])
        ]

    @property
    def available(self) -> bool:
        """Installed, or every model it needs can be downloaded."""
        return self.installed or all(i in self._catalog for i in MODEL_IDS)

    def download_mb(self) -> int:
        return sum(e.size_mb for e in self.missing())

    def set_enabled(self, on: bool) -> bool:
        """Switch it on (downloading first if needed) or off. False if it can't start."""
        if not on:
            self._apply(False)
            return True
        if self.installed:
            self._apply(True)
            return True
        if self.busy or not self.available:
            return False
        self._download()
        return True

    def _apply(self, on: bool) -> None:
        self._store.dispatch(a.UpdateConfigSection("speakers", {"separate_overlaps": on}))

    def _download(self) -> None:
        entries = self.missing()
        total = sum(e.size_mb for e in entries) << 20
        self.busy = True

        def run() -> None:
            manager = self._make_manager(self._models_dir())
            base = 0
            ok, message = True, "Ready."
            try:
                for entry in entries:
                    start = base

                    def report(done: int, _total: int, start: int = start) -> None:
                        self.progress.emit(min(start + done, total), total)

                    manager.download(entry, report, None)
                    base += entry.size_mb << 20
                ok = self.installed
                if ok:
                    self._apply(True)
                else:
                    message = "The download finished but a file is missing. Try again."
            except (DownloadCancelled, DownloadError) as exc:
                ok, message = False, str(exc) or "The download stopped. Try again."
            except Exception as exc:  # report, never crash the page
                logger.warning("separation download failed ({})", type(exc).__name__)
                ok, message = False, f"The download failed ({type(exc).__name__})."
            finally:
                self.busy = False
                self.finished.emit(ok, message)

        self._thread = threading.Thread(target=run, name="separation-download", daemon=True)
        self._thread.start()

    def wait(self, timeout: float = 30.0) -> None:
        """Tests: wait for the running download to end."""
        if self._thread is not None:
            self._thread.join(timeout)
