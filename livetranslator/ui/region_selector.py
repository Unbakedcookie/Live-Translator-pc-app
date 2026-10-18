"""Pick a screen region to translate (T082; spec §5.6; gate G5).

Every monitor gets a dimmed full-screen pane. Drag a rectangle (its size is shown next to
it), release to accept; Esc or a mere click cancels. The rectangle can cross monitors.

The returned `Region` is in **physical** screen pixels, read from Windows' own cursor position
at press and release, so it is right on any mix of monitor scalings (and matches what mss
captures). The panes only draw; Qt's logical coordinates are used for drawing alone.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QScreen,
)
from PySide6.QtWidgets import QWidget

from livetranslator.services.ocr.grab import Region
from livetranslator.theme.tokens import FONTS, RADIUS, SELECTOR, SPACE, Palette

HINT = "Drag around the text to translate · Esc cancels"
PhysicalCursor = Callable[[], tuple[int, int]]


def normalized_region(a: tuple[int, int], b: tuple[int, int]) -> Region:
    """The rectangle between two corners, whichever way the drag went."""
    left, right = sorted((a[0], b[0]))
    top, bottom = sorted((a[1], b[1]))
    return Region(left, top, right - left, bottom - top)


class _Pane(QWidget):
    """Dims one monitor and draws the part of the selection that falls on it."""

    def __init__(self, owner: RegionSelector, screen: QScreen) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.press(event.globalPosition().toPoint())
        else:
            self._owner.cancel()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._owner.move_to(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.release(event.globalPosition().toPoint())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._owner.cancel()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = self._owner.palette
        painter = QPainter(self)
        dim = QColor(p.bg)
        dim.setAlphaF(SELECTOR.dim_alpha)
        painter.fillRect(self.rect(), dim)
        selection = self._owner.selection_global()
        if selection is None:
            painter.setPen(QColor(p.text_primary))
            font = painter.font()
            font.setPointSize(FONTS.ui_size_large)
            painter.setFont(font)
            if self._owner.hint_pane is self:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, HINT)
            painter.end()
            return
        local = QRect(self.mapFromGlobal(selection.topLeft()), selection.size())
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(local, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(p.accent), SELECTOR.border_width))
        painter.drawRect(local)
        label = f"{selection.width()} × {selection.height()}"  # noqa: RUF001 - multiplication sign on purpose
        metrics = painter.fontMetrics()
        box = metrics.boundingRect(label).adjusted(-SPACE.sm, -SPACE.xs, SPACE.sm, SPACE.xs)
        box.moveTopLeft(local.bottomLeft() + QPoint(0, SPACE.xs))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(box, RADIUS.sm, RADIUS.sm)
        painter.setPen(QColor(p.text_primary))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


class RegionSelector(QObject):
    selected = Signal(object)  # Region (physical pixels)
    cancelled = Signal()

    def __init__(
        self,
        palette: Palette,
        cursor: PhysicalCursor | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.palette = palette
        self._cursor = cursor or _physical_cursor
        self.panes: list[_Pane] = []
        self.hint_pane: _Pane | None = None
        self._start_logical: QPoint | None = None
        self._current_logical: QPoint | None = None
        self._start_physical: tuple[int, int] | None = None

    def start(self) -> None:
        self.close()
        for screen in QGuiApplication.screens():
            pane = _Pane(self, screen)
            self.panes.append(pane)
            pane.show()
            if screen.geometry().contains(QCursor.pos()):
                self.hint_pane = pane
        if self.hint_pane is None and self.panes:
            self.hint_pane = self.panes[0]
        if self.hint_pane is not None:
            self.hint_pane.activateWindow()
            self.hint_pane.setFocus()

    def selection_global(self) -> QRect | None:
        if self._start_logical is None or self._current_logical is None:
            return None
        return QRect(self._start_logical, self._current_logical).normalized()

    def press(self, logical: QPoint) -> None:
        self._start_logical = self._current_logical = logical
        self._start_physical = self._cursor()

    def move_to(self, logical: QPoint) -> None:
        if self._start_logical is None:
            return
        self._current_logical = logical
        for pane in self.panes:
            pane.update()

    def release(self, logical: QPoint) -> None:
        if self._start_physical is None:
            return
        region = normalized_region(self._start_physical, self._cursor())
        self.close()
        if region.width < SELECTOR.min_size or region.height < SELECTOR.min_size:
            self.cancelled.emit()  # a click, not a drag
        else:
            self.selected.emit(region)

    def cancel(self) -> None:
        self.close()
        self.cancelled.emit()

    def close(self) -> None:
        for pane in self.panes:
            pane.close()
        self.panes = []
        self.hint_pane = None
        self._start_logical = self._current_logical = None
        self._start_physical = None


def _physical_cursor() -> tuple[int, int]:
    from livetranslator.platform.win32 import cursor_pos

    return cursor_pos()
