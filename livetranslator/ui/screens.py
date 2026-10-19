"""Qt monitor adapter for the pure geometry module (T021/T023)."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from livetranslator.ui.geometry import Monitor, Rect, beside


def rect_from_qrect(r: QRect) -> Rect:
    return Rect(r.x(), r.y(), r.width(), r.height())


def qrect_from_rect(r: Rect) -> QRect:
    return QRect(r.x, r.y, r.width, r.height)


def monitors() -> list[Monitor]:
    primary = QGuiApplication.primaryScreen()
    return [
        Monitor(
            name=s.name(),
            geometry=rect_from_qrect(s.geometry()),
            work=rect_from_qrect(s.availableGeometry()),
            primary=s is primary,
        )
        for s in QGuiApplication.screens()
    ]


def place_beside(window: QWidget, anchor: QWidget) -> None:
    """Move `window` next to `anchor` (right, else left, below, above; on its monitor) rather
    than over it, so neither hides the other."""
    screens = monitors()
    if not screens:
        return
    size = window.size()
    rect = beside(rect_from_qrect(anchor.frameGeometry()), screens, size.width(), size.height())
    window.move(rect.x, rect.y)
