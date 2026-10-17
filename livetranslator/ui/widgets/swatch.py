"""Palette swatches: a round preview of each theme, picked like a radio button (T022)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QWidget

from livetranslator.theme.tokens import PALETTES, SPACE, WINDOW, Palette

SWATCH = SPACE.xl + SPACE.xs  # 28 px


class PaletteSwatch(QAbstractButton):
    """Circle in the palette's background with its accent and first speaker colours."""

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette_value = palette
        self._ring = palette.accent
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(palette.name)
        self.setFixedSize(QSize(SWATCH, SWATCH))

    def set_palette(self, palette: Palette) -> None:
        self.palette_value = palette
        self.setToolTip(palette.name)
        self.update()

    def set_ring_color(self, color: str) -> None:
        """Selection ring colour (the owning window's accent)."""
        self._ring = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = self.palette_value
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = SPACE.xs // 2 + WINDOW.border_width
        outer = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        painter.setPen(QPen(QColor(p.border), WINDOW.border_width))
        painter.setBrush(QColor(p.bg))
        painter.drawEllipse(outer)
        dot = outer.width() / 4
        cy = outer.center().y() - dot / 2
        colors = (p.accent, p.speaker_me, p.speaker_others[0])
        start = outer.center().x() - 1.5 * dot
        painter.setPen(Qt.PenStyle.NoPen)
        for i, color in enumerate(colors):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(start + i * dot, cy, dot, dot))
        if self.isChecked():
            ring = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            painter.setPen(QPen(QColor(self._ring), SPACE.xs // 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring)
        painter.end()


class SwatchRow(QWidget):
    """One swatch per built-in palette; exactly one is selected."""

    palette_selected = Signal(str)  # palette id

    def __init__(self, current_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.xs)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.swatches: dict[str, PaletteSwatch] = {}
        for palette in PALETTES.values():
            swatch = PaletteSwatch(palette, self)
            self._group.addButton(swatch)
            layout.addWidget(swatch)
            self.swatches[palette.id] = swatch
            swatch.clicked.connect(lambda _c=False, pid=palette.id: self.palette_selected.emit(pid))
        layout.addStretch(1)
        self.set_current(current_id)

    def set_current(self, palette_id: str) -> None:
        swatch = self.swatches.get(palette_id)
        if swatch is not None:
            swatch.setChecked(True)
        else:  # custom palette: no built-in swatch selected
            self._group.setExclusive(False)
            for s in self.swatches.values():
                s.setChecked(False)
            self._group.setExclusive(True)

    def set_ring_color(self, color: str) -> None:
        for swatch in self.swatches.values():
            swatch.set_ring_color(color)
