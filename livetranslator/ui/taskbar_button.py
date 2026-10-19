"""The "Live Translator" taskbar button that minimized overlays come back from (user report
2026-10-18: "whenever I minimize the app it disappears and there's no way to bring it back").

Overlays are frameless tool windows: Windows gives them no taskbar button, and a minimized
frameless window can't be restored from the taskbar anyway (checked on this PC). So while any
overlay is minimized, this invisible stand-in sits minimized on the taskbar with the app's
name and icon. Clicking it (or its taskbar "Close window") emits `restore_requested`; the
stand-in never shows itself.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QWidget

from livetranslator.ui.session import session_ending


class TaskbarButton(QWidget):
    restore_requested = Signal()

    def __init__(self, title: str, window_icon: QIcon) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle(title)
        self.setWindowIcon(window_icon)
        self.setWindowOpacity(0.0)  # restoring flashes nothing: it hides again at once
        self.setFixedSize(1, 1)

    @property
    def on_taskbar(self) -> bool:
        return self.isVisible() and self.isMinimized()

    def set_on_taskbar(self, on: bool) -> None:
        if on and not self.on_taskbar:
            self.showMinimized()
        elif not on and self.isVisible():
            self.hide()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isVisible()
            and not self.isMinimized()
        ):
            # After the restore finishes: hiding inside it gets undone by the restore's show.
            QTimer.singleShot(0, self._restored)

    def _restored(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
            self.restore_requested.emit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if session_ending():
            event.accept()  # Windows is logging off / shutting down: never block it
            return
        event.ignore()  # "Close window" on the taskbar: bring the overlays back, don't quit
        self.hide()
        self.restore_requested.emit()
