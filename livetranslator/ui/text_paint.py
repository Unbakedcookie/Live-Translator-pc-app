"""Overlay text painting shared by the demo content (T024) and the chat line (T061).

Outline: the glyph path is stroked with a pen twice the visible width, then filled on top,
so exactly `width` px of outline shows outside each glyph.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen


def wrap_text(text: str, measure: Callable[[str], float], width: float) -> list[str]:
    """Greedy word wrap. A single word wider than `width` is broken by characters."""
    if width <= 0:
        return [text] if text else []
    rows: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if measure(candidate) <= width:
            current = candidate
            continue
        if current:
            rows.append(current)
            current = ""
        if measure(word) <= width:
            current = word
            continue
        piece = ""
        for ch in word:
            if measure(piece + ch) > width and piece:
                rows.append(piece)
                piece = ch
            else:
                piece += ch
        current = piece
    if current:
        rows.append(current)
    return rows


def draw_outlined_text(
    painter: QPainter,
    origin: QPointF,
    text: str,
    font: QFont,
    fill: QColor,
    outline: QColor | None,
    outline_width: int,
) -> None:
    """Draw `text` with its baseline starting at `origin`."""
    path = QPainterPath()
    path.addText(origin, font, text)
    if outline is not None and outline_width > 0:
        pen = QPen(outline, outline_width * 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
    painter.fillPath(path, fill)
