"""One chat-log line: layout and painting (T061; spec §5.2, gate G2). SHARED component.

    Mika  Okay! Wait for me at the gate.          <- label in the speaker colour, then text
          wrapped lines hang under the text       <- (stable = primary, changing = secondary)
          Wakatta, mon de mattete.                <- original, smaller ("original + translation")

The layout is computed from measuring functions only, so it is unit-tested without fonts;
painting reuses the overlay text painter (outline, shadow are the window's style).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter

from livetranslator.core.chat_view import ChatLineData, SpeakerKey
from livetranslator.core.state import WindowStyle
from livetranslator.theme.fonts import available_families, overlay_families
from livetranslator.theme.tokens import OVERLAY, SPACE, Palette, default_outline_width
from livetranslator.ui.text_paint import draw_outlined_text, wrap_text

Measure = Callable[[str], float]


class Role(StrEnum):
    LABEL = "label"
    STABLE = "stable"
    CHANGING = "changing"
    ORIGINAL = "original"
    TAG = "tag"  # "ZH→EN" after the label, small and dim


@dataclass(frozen=True)
class Run:
    x: float  # from the line's left edge
    text: str
    role: Role


@dataclass(frozen=True)
class Row:
    runs: tuple[Run, ...]
    original: bool = False  # drawn with the smaller original font


def _split_at(row: str, start: int, boundary: int) -> list[tuple[int, str, Role]]:
    """Cut `row` (which starts at `start` in the joined text) where stable text ends."""
    end = start + len(row)
    if boundary <= start:
        return [(0, row, Role.CHANGING)]
    if boundary >= end:
        return [(0, row, Role.STABLE)]
    cut = boundary - start
    stable, changing = row[:cut].rstrip(), row[cut:].lstrip()
    return [(0, stable, Role.STABLE), (len(row) - len(changing), changing, Role.CHANGING)]


def layout_rows(
    line: ChatLineData,
    width: float,
    measure_label: Measure,
    measure_text: Measure,
    measure_original: Measure,
) -> list[Row]:
    """Rows for `line` in a column `width` px wide. Text after the label wraps with a
    hanging indent at the label's width; stable and changing words share rows."""
    label = f"{line.label}  "
    label_width = measure_label(label)
    tag = f"{line.tag}  " if line.tag else ""
    indent = label_width + (measure_original(tag) if tag else 0.0)
    avail = max(width - indent, measure_text("M"))
    stable_words, changing_words = line.stable.split(), line.changing.split()
    joined = " ".join(stable_words + changing_words)
    boundary = len(" ".join(stable_words)) if stable_words else 0
    rows: list[Row] = []
    cursor = 0
    for i, text in enumerate(wrap_text(joined, measure_text, avail) or [""]):
        start = joined.find(text, cursor) if text else cursor
        cursor = start + len(text)
        runs: list[Run] = []
        if i == 0:
            runs.append(Run(0.0, label, Role.LABEL))
            if tag:
                runs.append(Run(label_width, tag, Role.TAG))
        for offset, piece, role in _split_at(text, start, boundary):
            if piece:
                runs.append(Run(indent + measure_text(text[:offset]), piece, role))
        rows.append(Row(tuple(runs)))
    if line.original:
        for text in wrap_text(line.original, measure_original, avail):
            rows.append(Row((Run(indent, text, Role.ORIGINAL),), original=True))
    return rows


@dataclass(frozen=True)
class ChatFonts:
    label: QFont
    text: QFont
    original: QFont

    @property
    def text_metrics(self) -> QFontMetricsF:
        return QFontMetricsF(self.text)

    @property
    def original_metrics(self) -> QFontMetricsF:
        return QFontMetricsF(self.original)

    def row_height(self, row: Row) -> float:
        return (self.original_metrics if row.original else self.text_metrics).height()


def chat_fonts(style: WindowStyle, language: str | None) -> ChatFonts:
    families = overlay_families(style.font_family, language, available_families())

    def make(bold: bool, scale: float) -> QFont:
        font = QFont()
        if families:
            font.setFamilies(families)
        font.setPointSizeF(style.font_size * scale)
        if bold:
            font.setWeight(QFont.Weight.DemiBold)
        return font

    return ChatFonts(
        label=make(True, 1.0), text=make(False, 1.0), original=make(False, OVERLAY.original_scale)
    )


def layout_line(line: ChatLineData, width: float, fonts: ChatFonts) -> list[Row]:
    return layout_rows(
        line,
        width,
        QFontMetricsF(fonts.label).horizontalAdvance,
        fonts.text_metrics.horizontalAdvance,
        fonts.original_metrics.horizontalAdvance,
    )


def rows_height(rows: Sequence[Row], fonts: ChatFonts) -> float:
    if not rows:
        return 0.0
    return sum(fonts.row_height(r) for r in rows) + SPACE.xs * (len(rows) - 1)


def speaker_color(palette: Palette, speaker: SpeakerKey) -> str:
    if speaker == "me":
        return palette.speaker_me
    if speaker == "screen":
        return palette.speaker_screen
    return palette.speaker_color(speaker if isinstance(speaker, int) else 0)


def paint_rows(
    painter: QPainter,
    rows: Sequence[Row],
    left: float,
    top: float,
    fonts: ChatFonts,
    palette: Palette,
    style: WindowStyle,
    speaker: SpeakerKey,
) -> None:
    """Draw `rows` with their top-left corner at (left, top)."""
    colors = {
        Role.LABEL: QColor(speaker_color(palette, speaker)),
        Role.STABLE: QColor(palette.text_primary),
        Role.CHANGING: QColor(palette.text_secondary),
        Role.ORIGINAL: QColor(palette.text_secondary),
        Role.TAG: QColor(palette.text_secondary),
    }
    role_fonts = {
        Role.LABEL: fonts.label,
        Role.STABLE: fonts.text,
        Role.CHANGING: fonts.text,
        Role.ORIGINAL: fonts.original,
        Role.TAG: fonts.original,
    }
    outline = QColor(palette.outline) if style.outline else None
    outline_px = style.outline_width or default_outline_width(palette)
    y = top
    for row in rows:
        metrics = fonts.original_metrics if row.original else fonts.text_metrics
        baseline = y + metrics.ascent()
        for run in row.runs:
            draw_outlined_text(
                painter,
                QPointF(left + run.x, baseline),
                run.text,
                role_fonts[run.role],
                colors[run.role],
                outline,
                outline_px,
            )
        y += metrics.height() + SPACE.xs
