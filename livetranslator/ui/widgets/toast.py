"""Short self-dismissing notice near a window, e.g. the click-through hotkey hint (T022;
spec §3.4)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from livetranslator.theme.tokens import MOTION, RADIUS, SPACE, Palette


class Toast(QWidget):
    def __init__(self, text: str, palette: Palette, duration_ms: int = MOTION.toast_ms) -> None:
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._palette = palette
        self.label = QLabel(text, self)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(f"color: {palette.text_primary};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE.md, SPACE.sm, SPACE.md, SPACE.sm)
        layout.addWidget(self.label)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(duration_ms)
        self._timer.timeout.connect(self.close)

    def show_at(self, anchor: QPoint) -> None:
        """Show centred horizontally on `anchor` (global coordinates), just below it."""
        self.adjustSize()
        self.move(anchor.x() - self.width() // 2, anchor.y() + SPACE.sm)
        self.show()
        self._timer.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self._palette.border))
        painter.setBrush(QColor(self._palette.surface))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()
