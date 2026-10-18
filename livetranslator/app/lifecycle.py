"""Export and quit (T063/T064; spec §5.11).

- `Exporter` asks where to save, renders the chosen format and writes it. This is the only
  place a transcript ever reaches the disk, and only because the user asked.
- `QuitFlow`: with nothing said, quit at once. Otherwise ask "Export this conversation
  before closing?" → Export… (quit only if it was saved), Close without saving, or Cancel.
Dialogs are injected so the logic is tested without clicking.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QWidget

from livetranslator import APP_DISPLAY_NAME
from livetranslator.core.export import transcript_json, transcript_lines, transcript_txt
from livetranslator.core.store import Store
from livetranslator.ui.dialogs import QuitChoice

AskPath = Callable[[QWidget | None, Path], Path | None]
AskQuit = Callable[[QWidget | None], QuitChoice]


def default_export_dir() -> Path:
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(documents) if documents else Path.home()


def suggested_name(now: datetime) -> str:
    return f"{APP_DISPLAY_NAME} {now:%Y-%m-%d %H%M}.txt"


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 via a temp file in the same folder, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".export-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Exporter:
    def __init__(
        self,
        store: Store,
        ask_path: AskPath,
        clock: Callable[[], datetime] = datetime.now,
        folder: Callable[[], Path] = default_export_dir,
    ) -> None:
        self._store = store
        self._ask_path = ask_path
        self._clock = clock
        self._folder = folder
        self.last_error = ""

    def export(self, parent: QWidget | None = None) -> Path | None:
        """Ask for a file and save the conversation. None if cancelled or it failed (then
        `last_error` says why in plain words)."""
        self.last_error = ""
        now = self._clock()
        path = self._ask_path(parent, self._folder() / suggested_name(now))
        if path is None:
            return None
        state = self._store.state
        is_json = path.suffix.lower() == ".json"
        text = transcript_json(state, now) if is_json else transcript_txt(state, now)
        try:
            write_text_atomic(path, text)
        except OSError as exc:
            logger.warning("export failed ({})", type(exc).__name__)  # no path: may hold names
            self.last_error = f"Couldn't save there ({exc.strerror or type(exc).__name__})."
            return None
        logger.info("conversation exported ({})", "json" if is_json else "txt")
        return path


class QuitFlow:
    def __init__(
        self,
        store: Store,
        exporter: Exporter,
        ask_quit: AskQuit,
        quit_app: Callable[[], None],
        show_error: Callable[[str], None] | None = None,
    ) -> None:
        self._store = store
        self._exporter = exporter
        self._ask_quit = ask_quit
        self._quit_app = quit_app
        self._show_error = show_error
        self._asking = False

    def request_quit(self, parent: QWidget | None = None) -> bool:
        """True if the app is quitting."""
        if self._asking:
            return False  # a second Quit while the question is open: ignore it
        if not transcript_lines(self._store.state):
            self._quit_app()
            return True
        self._asking = True
        try:
            choice = self._ask_quit(parent)
            if choice is QuitChoice.EXPORT and self._exporter.export(parent) is None:
                if self._exporter.last_error and self._show_error is not None:
                    self._show_error(self._exporter.last_error)
                return False  # save dialog cancelled or failed: stay open
            if choice is QuitChoice.CANCEL:
                return False
        finally:
            self._asking = False
        self._quit_app()
        return True
