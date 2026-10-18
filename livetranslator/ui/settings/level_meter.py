"""A thin horizontal loudness bar for Settings → Audio (T072; spec §5.8)."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from livetranslator.services.audio.level import meter_fraction
from livetranslator.theme.tokens import SETTINGS, Palette


class LevelMeter(QWidget):
    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self.fraction = 0.0
        self.active = False
        self.setFixedSize(SETTINGS.meter_width, SETTINGS.meter_height)

    def set_level(self, db: float | None) -> None:
        """dBFS of the latest slice; None = the stream isn't capturing (empty, dimmed)."""
        self.active = db is not None
        self.fraction = 0.0 if db is None else meter_fraction(db)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(p.border))
        radius = self.height() / 2
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QColor(p.surface_alt))
        painter.drawRoundedRect(rect, radius, radius)
        if self.active and self.fraction > 0:
            filled = QRectF(rect.x(), rect.y(), rect.width() * self.fraction, rect.height())
            painter.setPen(QColor(p.accent))
            painter.setBrush(QColor(p.accent))
            painter.drawRoundedRect(filled, radius, radius)
        painter.end()
