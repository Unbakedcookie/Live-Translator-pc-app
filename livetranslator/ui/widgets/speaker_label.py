"""Inline speaker rename (T104; spec §5.13 "click any label → inline rename").

A small popup box placed right over the clicked label, pre-filled and selected. Enter saves,
Esc or clicking elsewhere cancels, an empty box goes back to the automatic name
("Speaker 2"). It is its own popup window because overlays never take keyboard focus (they
must not steal it from a game).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QVBoxLayout, QWidget

from livetranslator.theme.qss import window_qss
from livetranslator.theme.tokens import RADIUS, SETTINGS, SPACE, Palette

NAME_MAX = 32
HINT = "Enter saves · empty = automatic name"


class RenamePopup(QFrame):
    renamed = Signal(str)  # "" = back to the automatic name

    def __init__(
        self, current: str, automatic: str, palette: Palette, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._palette = palette
        self.setStyleSheet(window_qss(palette))
        self.edit = QLineEdit(current, self)
        self.edit.setPlaceholderText(automatic)
        self.edit.setMaxLength(NAME_MAX)
        self.edit.setMinimumWidth(SETTINGS.number_width * 2)
        self.edit.selectAll()
        self.edit.installEventFilter(self)
        self.hint = QLabel(HINT, self)
        self.hint.setStyleSheet(f"color: {palette.text_secondary}; background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE.xs, SPACE.xs, SPACE.xs, SPACE.xs)
        layout.setSpacing(SPACE.xs)
        layout.addWidget(self.edit)
        layout.addWidget(self.hint)

    def open_at(self, global_top_left: QPoint) -> None:
        self.adjustSize()
        self.move(global_top_left - QPoint(SPACE.xs, SPACE.xs))
        self.show()
        self.activateWindow()
        self.edit.setFocus()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.edit and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)  # nosec B101 - Qt guarantees the type
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.renamed.emit(self.edit.text().strip())
                self.close()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self._palette.border))
        painter.setBrush(QColor(self._palette.surface))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()
