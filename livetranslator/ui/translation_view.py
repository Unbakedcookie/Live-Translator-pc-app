"""The chat log inside a floating window (T062; spec §5.2).

Painted as one widget, bottom-anchored like a chat: the newest line sits at the bottom.
Only the newest MAX_LINES lines this window shows are kept (the full log stays in the store
for the transcript window). Each line's layout is cached and redone only when its text,
the width or the font changes, so a partial line updating several times a second redraws
without re-measuring the rest (and without flicker: nothing is re-created).

Scrolling: the wheel scrolls back through older lines. While scrolled up, new lines don't
move what you're reading; `unread_changed(True)` lets the window show a "New lines" pill
that jumps back to the bottom.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from livetranslator.core.chat_view import ChatLineData, visible_lines
from livetranslator.core.state import WindowConfig, WindowStyle
from livetranslator.core.store import Store
from livetranslator.theme.tokens import OVERLAY, SPACE, Palette
from livetranslator.ui.widgets.chat_line import (
    ChatFonts,
    Row,
    chat_fonts,
    layout_line,
    paint_rows,
    rows_height,
)

MAX_LINES = 200
EMPTY_MESSAGE = "Translations appear here"
WHEEL_ROWS = 3  # rows scrolled per wheel notch


class TranslationView(QWidget):
    unread_changed = Signal(bool)

    def __init__(self, store: Store, window_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The window handles the mouse (drag anywhere); it forwards the wheel to scroll_by.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._store = store
        self._window_id = window_id
        self._palette: Palette | None = None
        self._style = WindowStyle()
        self._fonts: ChatFonts | None = None
        self._fonts_key: tuple[object, ...] = ()
        self.lines: list[ChatLineData] = []
        self._layouts: dict[str, tuple[ChatLineData, float, list[Row]]] = {}
        self._offset = 0.0  # px scrolled up from the bottom
        self.unread = False
        self.label_hits: list[tuple[QRectF, str]] = []  # (label rect, utterance id), T104
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(OVERLAY.shadow_blur)
        self._shadow.setOffset(OVERLAY.shadow_offset, OVERLAY.shadow_offset)
        self._shadow.setEnabled(False)
        self.setGraphicsEffect(self._shadow)
        store.utterance_added.connect(self._on_session_change)
        store.utterance_updated.connect(self._on_session_change)
        store.utterance_removed.connect(self._on_session_change)
        store.session_cleared.connect(self.refresh)
        store.speaker_changed.connect(self._on_session_change)
        store.config_changed.connect(self._on_session_change)  # e.g. my language, "Me" label

    # ------------------------------------------------------------ inputs

    def set_view(self, palette: Palette, cfg: WindowConfig) -> None:
        self._palette, self._style = palette, cfg.style
        key = (cfg.style.font_family, cfg.style.font_size, cfg.target_lang)
        if key != self._fonts_key or self._fonts is None:
            self._fonts_key = key
            self._fonts = chat_fonts(cfg.style, cfg.target_lang)
            self._layouts.clear()
        self._shadow.setColor(QColor(palette.outline))
        self._shadow.setEnabled(cfg.style.shadow)
        self.refresh()

    def _on_session_change(self, _key: str = "") -> None:
        self.refresh()

    def refresh(self) -> None:
        cfg = self._store.state.config.window(self._window_id)
        if cfg is None:
            return
        old_total = self.content_height()
        old_last = self.lines[-1].utterance_id if self.lines else None
        self.lines = visible_lines(self._store.state, cfg, MAX_LINES)
        keep = {line.utterance_id for line in self.lines}
        self._layouts = {k: v for k, v in self._layouts.items() if k in keep}
        if self._offset > 0:
            # Keep what the user is reading still: grow the offset by what was added below.
            grown = self._offset + self.content_height() - old_total
            self._offset = min(max(grown, 0.0), self.max_offset())
            new_last = self.lines[-1].utterance_id if self.lines else None
            if new_last != old_last and new_last is not None:
                self._set_unread(True)
        self.update()

    # ------------------------------------------------------------ layout

    def _width(self) -> float:
        return float(self.width() - 2 * SPACE.md)

    def rows_for(self, line: ChatLineData) -> list[Row]:
        fonts = self._fonts
        if fonts is None:
            return []
        width = self._width()
        cached = self._layouts.get(line.utterance_id)
        if cached is not None and cached[0] == line and cached[1] == width:
            return cached[2]
        rows = layout_line(line, width, fonts)
        self._layouts[line.utterance_id] = (line, width, rows)
        return rows

    def _line_height(self, line: ChatLineData) -> float:
        return rows_height(self.rows_for(line), self._fonts) if self._fonts else 0.0

    def content_height(self) -> float:
        if not self.lines:
            return 0.0
        heights = [self._line_height(line) for line in self.lines]
        return sum(heights) + OVERLAY.line_gap * (len(heights) - 1)

    def _viewport_height(self) -> float:
        return float(self.height() - 2 * SPACE.sm)

    def max_offset(self) -> float:
        return max(self.content_height() - self._viewport_height(), 0.0)

    # ------------------------------------------------------------ scrolling

    @property
    def offset(self) -> float:
        return self._offset

    def wheel_step(self) -> float:
        rows = self._fonts.text_metrics.height() if self._fonts else float(SPACE.lg)
        return WHEEL_ROWS * rows

    def scroll_by(self, px: float) -> None:
        """Positive = towards older lines."""
        self._offset = min(max(self._offset + px, 0.0), self.max_offset())
        if self._offset == 0.0:
            self._set_unread(False)
        self.update()

    def scroll_to_bottom(self) -> None:
        self._offset = 0.0
        self._set_unread(False)
        self.update()

    def _set_unread(self, unread: bool) -> None:
        if unread != self.unread:
            self.unread = unread
            self.unread_changed.emit(unread)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._offset = min(self._offset, self.max_offset())

    # ------------------------------------------------------------ painting

    def paintEvent(self, event: QPaintEvent) -> None:
        palette, fonts = self._palette, self._fonts
        if palette is None or fonts is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.lines:
            painter.setFont(fonts.text)
            painter.setPen(QColor(palette.text_secondary))
            painter.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, EMPTY_MESSAGE)
            painter.end()
            return
        painter.setClipRect(self.rect())
        bottom = self.height() - SPACE.sm + self._offset
        hits: list[tuple[QRectF, str]] = []
        label_metrics = QFontMetricsF(fonts.label)
        for line in reversed(self.lines):
            if bottom < 0:
                break
            rows = self.rows_for(line)
            top = bottom - rows_height(rows, fonts)
            if top < self.height():
                paint_rows(painter, rows, SPACE.md, top, fonts, palette, self._style, line.speaker)
                if rows:  # T104: remember where the speaker label is, for click-to-rename
                    width = label_metrics.horizontalAdvance(line.label)
                    hits.append(
                        (QRectF(SPACE.md, top, width, fonts.row_height(rows[0])), line.utterance_id)
                    )
            bottom = top - OVERLAY.line_gap
        painter.end()
        self.label_hits = hits

    def label_at(self, point: QPointF) -> str | None:
        """The utterance whose speaker label was painted at `point` (view coordinates)."""
        return next((uid for rect, uid in self.label_hits if rect.contains(point)), None)
