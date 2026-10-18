"""The overlay's problem line (T111; spec §9): an icon and the most serious current status,
e.g. "No microphone found. Check Windows sound settings." Hidden when all is well."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from livetranslator.core.state import RuntimeStatus, StatusLevel
from livetranslator.core.status_view import headline
from livetranslator.core.store import Store
from livetranslator.theme.icons import IconRole, icon
from livetranslator.theme.tokens import FONTS, SPACE, WINDOW, Palette

ICONS: dict[StatusLevel, tuple[str, IconRole]] = {
    StatusLevel.ERROR: ("warning-circle", "danger"),
    StatusLevel.WARNING: ("warning", "danger"),
    StatusLevel.BUSY: ("hourglass", "text_secondary"),
}


class StatusStrip(QWidget):
    changed = Signal()

    def __init__(self, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._palette: Palette | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # drag still works
        self.icon = QLabel(self)
        self.text = QLabel(self)
        font = QFont(FONTS.ui_family)
        font.setPointSize(FONTS.ui_size_small)
        self.text.setFont(font)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.xs)
        layout.addWidget(self.icon)
        layout.addWidget(self.text, 1)
        self.shown: RuntimeStatus | None = None
        store.runtime_changed.connect(self._on_runtime)

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.text.setStyleSheet(f"color: {palette.text_primary}; background: transparent;")
        self.shown = None  # redraw the icon in the new colours
        self.refresh()

    def _on_runtime(self, key: str) -> None:
        if key.startswith("status:"):
            self.refresh()

    def refresh(self) -> None:
        status = headline(self._store.state.runtime.statuses)
        if status == self.shown:
            return
        self.shown = status
        if status is not None and self._palette is not None:
            name, role = ICONS[status.level]
            size = WINDOW.icon_size
            self.icon.setPixmap(icon(name, self._palette, role).pixmap(QSize(size, size)))
            self.text.setText(status.message)
        self.changed.emit()  # the window shows/hides the strip and relays out
