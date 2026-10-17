"""Demo lines for the G1 look-and-feel review (T024; spec M02: "demo text is sample lines").

Shows how overlay text looks with the window's palette, font, outline, shadow and display
mode before any engine exists. Replaced by the live TranslationView in T062.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPaintEvent
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from livetranslator.core.state import DisplayMode, Source, WindowStyle
from livetranslator.theme.fonts import available_families, overlay_families
from livetranslator.theme.tokens import OVERLAY, SPACE, Palette, default_outline_width
from livetranslator.ui.text_paint import draw_outlined_text, wrap_text


@dataclass(frozen=True)
class SampleLine:
    source: Source
    speaker: str  # "me", "screen", or an index into the others ramp
    label: str
    translation: str
    original: str | None
    tentative: bool = False


SAMPLE_LINES: tuple[SampleLine, ...] = (
    SampleLine(Source.ME, "me", "Me", "Ready when you are, let's go!", None),
    SampleLine(
        Source.OTHERS,
        "0",
        "Mika",
        "Okay! Wait for me at the gate.",
        "わかった！門で待ってて。",  # noqa: RUF001 - real Japanese punctuation
    ),
    SampleLine(
        Source.OTHERS,
        "1",
        "Speaker 2",
        "I think we should take the left path and",
        "Creo que deberíamos ir por el camino izquierdo y",
        tentative=True,
    ),
    SampleLine(
        Source.SCREEN, "screen", "Screen", "Quest complete: return to town", "Quête terminée"
    ),
)


class SampleContent(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._palette: Palette | None = None
        self._style = WindowStyle()
        self._display = DisplayMode.TRANSLATION
        self._sources: tuple[Source, ...] = (Source.ME, Source.OTHERS)
        self._language = "en"
        self._families: list[str] = []
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(OVERLAY.shadow_blur)
        self._shadow.setOffset(OVERLAY.shadow_offset, OVERLAY.shadow_offset)
        self._shadow.setEnabled(False)
        self.setGraphicsEffect(self._shadow)

    def set_view(
        self,
        palette: Palette,
        style: WindowStyle,
        display: DisplayMode,
        sources: tuple[Source, ...],
        language: str,
    ) -> None:
        self._palette, self._style, self._display = palette, style, display
        self._sources, self._language = sources, language
        self._families = overlay_families(style.font_family, language, available_families())
        self._shadow.setColor(QColor(palette.outline))
        self._shadow.setEnabled(style.shadow)
        self.update()

    def _font(self, bold: bool, scale: float = 1.0) -> QFont:
        font = QFont()
        if self._families:
            font.setFamilies(self._families)
        font.setPointSizeF(self._style.font_size * scale)
        if bold:
            font.setWeight(QFont.Weight.DemiBold)
        return font

    def _speaker_color(self, key: str) -> str:
        p = self._palette
        if p is None:
            return ""
        if key == "me":
            return p.speaker_me
        if key == "screen":
            return p.speaker_screen
        return p.speaker_color(int(key))

    def paintEvent(self, event: QPaintEvent) -> None:
        p = self._palette
        if p is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        label_font = self._font(bold=True)
        text_font = self._font(bold=False)
        original_font = self._font(bold=False, scale=0.8)
        label_metrics = QFontMetricsF(label_font)
        text_metrics = QFontMetricsF(text_font)
        original_metrics = QFontMetricsF(original_font)
        outline = QColor(p.outline) if self._style.outline else None
        width_px = self._style.outline_width or default_outline_width(p)
        avail = self.width() - 2 * SPACE.md

        # Build rows (font, colour, x, text) top-down, then draw them bottom-anchored like a chat.
        rows: list[tuple[QFont, QFontMetricsF, list[tuple[float, str, QColor]]]] = []
        for line in SAMPLE_LINES:
            if line.source not in self._sources:
                continue
            label = f"{line.label} "
            label_w = label_metrics.horizontalAdvance(label)
            fill = QColor(p.text_secondary if line.tentative else p.text_primary)
            wrapped = wrap_text(line.translation, text_metrics.horizontalAdvance, avail - label_w)
            for i, text in enumerate(wrapped):
                parts: list[tuple[float, str, QColor]] = []
                if i == 0:
                    parts.append((0.0, label, QColor(self._speaker_color(line.speaker))))
                parts.append((label_w, text, fill))
                rows.append((text_font, text_metrics, parts))
            if self._display is DisplayMode.BOTH and line.original:
                for text in wrap_text(
                    line.original, original_metrics.horizontalAdvance, avail - label_w
                ):
                    rows.append(
                        (
                            original_font,
                            original_metrics,
                            [(label_w, text, QColor(p.text_secondary))],
                        )
                    )

        y = float(self.height() - SPACE.sm)
        for font, metrics, parts in reversed(rows):
            baseline = y - metrics.descent()
            if baseline - metrics.ascent() < 0:
                break
            for x, text, color in parts:
                draw_outlined_text(
                    painter,
                    QPointF(SPACE.md + x, baseline),
                    text,
                    label_font if x == 0.0 and font is text_font else font,
                    color,
                    outline,
                    width_px,
                )
            y -= metrics.height() + SPACE.xs
        painter.end()
