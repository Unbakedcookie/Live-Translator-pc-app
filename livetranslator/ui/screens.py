"""Qt monitor adapter for the pure geometry module (T021/T023)."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

from livetranslator.ui.geometry import Monitor, Rect


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
