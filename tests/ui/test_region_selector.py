"""T082 — region selector: physical-pixel result, cancel paths, one pane per monitor."""

import sys

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

from livetranslator.services.ocr.grab import Region
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.region_selector import RegionSelector, normalized_region

PALETTE = PALETTES[DEFAULT_PALETTE_ID]


def test_normalized_region_any_drag_direction():
    assert normalized_region((100, 50), (300, 90)) == Region(100, 50, 200, 40)
    assert normalized_region((300, 90), (100, 50)) == Region(100, 50, 200, 40)
    assert normalized_region((300, 50), (100, 90)) == Region(100, 50, 200, 40)


class FakeCursor:
    """Physical cursor positions, as Windows would report them (scaled 1.5x here)."""

    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []

    def __call__(self) -> tuple[int, int]:
        return self.points.pop(0)


def make(qtbot):
    cursor = FakeCursor()
    selector = RegionSelector(PALETTE, cursor)
    got: list[object] = []
    cancelled: list[int] = []
    selector.selected.connect(got.append)
    selector.cancelled.connect(lambda: cancelled.append(1))
    return selector, cursor, got, cancelled


@pytest.mark.skipif(sys.platform != "win32", reason="real windows")
def test_drag_returns_the_physical_rectangle(qtbot):
    selector, cursor, got, cancelled = make(qtbot)
    selector.start()
    assert len(selector.panes) == len(QGuiApplication.screens())
    assert all(p.isVisible() for p in selector.panes)
    cursor.points = [(150, 75), (450, 135)]  # what Windows reports (physical)
    selector.press(QPoint(100, 50))  # what Qt reports (logical)
    selector.move_to(QPoint(300, 90))
    sel = selector.selection_global()
    assert sel is not None and (sel.width(), sel.height()) == (201, 41)  # QRect is inclusive
    selector.release(QPoint(300, 90))
    assert got == [Region(150, 75, 300, 60)] and cancelled == []
    assert selector.panes == []  # closed


@pytest.mark.skipif(sys.platform != "win32", reason="real windows")
def test_click_and_escape_cancel(qtbot):
    selector, cursor, got, cancelled = make(qtbot)
    selector.start()
    cursor.points = [(10, 10), (12, 13)]  # a click: smaller than the minimum size
    selector.press(QPoint(10, 10))
    selector.release(QPoint(12, 13))
    assert got == [] and cancelled == [1]
    selector.start()
    selector.cancel()  # Esc / right click
    assert cancelled == [1, 1] and selector.panes == []
    selector.release(QPoint(0, 0))  # stray release after closing: ignored
    assert got == []
