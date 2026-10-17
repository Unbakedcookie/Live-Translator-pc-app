"""Render every palette as a mock overlay window, for the G1 look-and-feel review (T012).

Dev tool, not shipped. Each panel is drawn at the default background opacity over a busy,
game-like backdrop so readability is judged where it matters. The chat lines only preview
colours and fonts; the real chat-line component is T061 (gate G2).

    python -m tools.palette_preview --out preview.png [--seed "#3B82F6"]   (from the repo root)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication

from livetranslator.theme.fonts import bundled_font_files, register_fonts
from livetranslator.theme.icons import IconRole, icon
from livetranslator.theme.palette_gen import generate_palette
from livetranslator.theme.tokens import FONTS, OVERLAY, PALETTES, RADIUS, SPACE, WINDOW, Palette

PANEL_W = WINDOW.default_width
PANEL_H = WINDOW.default_height + 40
GAP = SPACE.xl
CAPTION_H = 28
PREVIEW_FONT_PT = 14  # a little below the 16 pt default so four lines fit the default size

LINES: list[tuple[str, str, str]] = [
    # (speaker key, label, text). Speaker keys: me / screen / others index as a digit.
    ("me", "Me", "Ready when you are, let's go!"),
    ("0", "Mika", "Okay! Wait for me at the gate."),
    ("1", "Speaker 2", "I think we should take the left path and"),
    ("screen", "Screen", "Quest complete: return to town"),
]


def _color(value: str, alpha: float = 1.0) -> QColor:
    c = QColor(value)
    c.setAlphaF(alpha)
    return c


def draw_backdrop(p: QPainter, size: QSize) -> None:
    """A colourful, high-detail stand-in for a game scene."""
    grad = QLinearGradient(0, 0, size.width(), size.height())
    for stop, value in ((0.0, "#2B5876"), (0.35, "#C4A35A"), (0.6, "#4E7D3A"), (1.0, "#A23B3B")):
        grad.setColorAt(stop, QColor(value))
    p.fillRect(0, 0, size.width(), size.height(), grad)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(0, size.width() + size.height(), 18):
        p.setBrush(QColor(255, 255, 255, 40) if (i // 18) % 2 else QColor(0, 0, 0, 40))
        path = QPainterPath()
        path.moveTo(i, 0)
        path.lineTo(i + 9, 0)
        path.lineTo(i + 9 - size.height(), size.height())
        path.lineTo(i - size.height(), size.height())
        path.closeSubpath()
        p.drawPath(path)


def draw_outlined_text(
    p: QPainter, pos: QPointF, text: str, font: QFont, fill: QColor, outline: QColor
) -> float:
    path = QPainterPath()
    path.addText(pos, font, text)
    pen = QPen(outline, OVERLAY.outline_width_default * 2)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.strokePath(path, pen)
    p.fillPath(path, fill)
    return QFontMetricsF(font).horizontalAdvance(text)


def speaker_color(palette: Palette, key: str) -> str:
    if key == "me":
        return palette.speaker_me
    if key == "screen":
        return palette.speaker_screen
    return palette.speaker_color(int(key))


def draw_panel(p: QPainter, x: float, y: float, palette: Palette, caption: str) -> None:
    caption_font = QFont(FONTS.ui_family, FONTS.ui_size_large)
    caption_font.setWeight(QFont.Weight.DemiBold)
    p.setFont(caption_font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(x, y, PANEL_W, CAPTION_H), Qt.AlignmentFlag.AlignVCenter, caption)
    top = y + CAPTION_H
    panel = QRectF(x, top, PANEL_W, PANEL_H)

    body = QPainterPath()
    body.addRoundedRect(panel, RADIUS.md, RADIUS.md)
    p.fillPath(body, _color(palette.bg, WINDOW.bg_opacity_default))

    chrome = QPainterPath()
    chrome.addRoundedRect(QRectF(x, top, PANEL_W, WINDOW.chrome_height), RADIUS.md, RADIUS.md)
    chrome.addRect(QRectF(x, top + RADIUS.md, PANEL_W, WINDOW.chrome_height - RADIUS.md))
    p.fillPath(chrome.simplified(), _color(palette.surface))

    size = WINDOW.icon_size
    icon_y = top + (WINDOW.chrome_height - size) / 2
    icon("push-pin-fill", palette, "accent").paint(p, int(x + SPACE.sm), int(icon_y), size, size)
    title_font = QFont(FONTS.ui_family, FONTS.ui_size)
    title_font.setWeight(QFont.Weight.Medium)
    p.setFont(title_font)
    p.setPen(QColor(palette.text_primary))
    p.drawText(
        QRectF(x + SPACE.sm * 2 + size, top, 300, WINDOW.chrome_height),
        Qt.AlignmentFlag.AlignVCenter,
        "English  ·  Others + Me",
    )
    right_icons: list[tuple[str, IconRole]] = [
        ("palette", "text_secondary"),
        ("gear", "text_secondary"),
        ("minus", "text_secondary"),
        ("x", "text_secondary"),
    ]
    for i, (name, role) in enumerate(reversed(right_icons)):
        ix = x + PANEL_W - SPACE.sm - size - i * (size + SPACE.sm)
        icon(name, palette, role).paint(p, int(ix), int(icon_y), size, size)

    label_font = QFont(FONTS.overlay_family, PREVIEW_FONT_PT)
    label_font.setWeight(QFont.Weight.DemiBold)
    text_font = QFont(FONTS.overlay_family, PREVIEW_FONT_PT)
    outline = QColor(palette.outline)
    line_h = QFontMetricsF(text_font).height() + SPACE.sm
    baseline = top + WINDOW.chrome_height + SPACE.md + QFontMetricsF(text_font).ascent()
    for key, label, text in LINES:
        px = x + SPACE.md
        px += draw_outlined_text(
            p,
            QPointF(px, baseline),
            label,
            label_font,
            QColor(speaker_color(palette, key)),
            outline,
        )
        px += SPACE.sm
        tentative = key == "1"
        fill = QColor(palette.text_secondary if tentative else palette.text_primary)
        draw_outlined_text(p, QPointF(px, baseline), text, text_font, fill, outline)
        baseline += line_h

    swatch = SPACE.md
    sx = x + SPACE.md
    sy = top + PANEL_H - SPACE.md - swatch
    p.setPen(Qt.PenStyle.NoPen)
    for value in (palette.speaker_me, *palette.speaker_others, palette.speaker_screen):
        p.setBrush(QColor(value))
        p.drawEllipse(QRectF(sx, sy, swatch, swatch))
        sx += swatch + SPACE.sm
    p.setBrush(QColor(palette.accent))
    p.drawRoundedRect(QRectF(sx + SPACE.md, sy, swatch * 3, swatch), RADIUS.sm, RADIUS.sm)


def render(out: Path, seed: str) -> None:
    panels: list[tuple[Palette, str]] = [(p, p.name) for p in PALETTES.values()]
    custom = generate_palette(seed, dark=True)
    panels.append((custom, f"Custom from one colour {seed} (dark)"))
    cols = 3
    rows = (len(panels) + cols - 1) // cols
    width = cols * PANEL_W + (cols + 1) * GAP
    height = rows * (PANEL_H + CAPTION_H) + (rows + 1) * GAP
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    draw_backdrop(painter, image.size())
    for i, (palette, caption) in enumerate(panels):
        col, row = i % cols, i // cols
        x = GAP + col * (PANEL_W + GAP)
        y = GAP + row * (PANEL_H + CAPTION_H + GAP)
        draw_panel(painter, x, y, palette, caption)
    painter.end()
    if not image.save(str(out)):
        raise OSError(f"could not write {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the palette preview sheet.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", default="#3B82F6", help="seed colour for the custom palette")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    register_fonts(bundled_font_files())
    render(args.out, args.seed)
    print(f"wrote {args.out} ({app.applicationName() or 'preview'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
