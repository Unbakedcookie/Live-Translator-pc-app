"""Transcript window (T063; spec §5.11): the whole conversation in every language, with
search, copy and export.

It lists every line regardless of which overlay shows it: original text under a coloured
speaker heading, then each translation. Search filters lines (speaker, text or any
translation). Text can be selected and copied normally; "Copy" takes everything shown.
It redraws a moment after the store changes (batched), keeping the view at the bottom when
it was already there.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from livetranslator.core.export import TranscriptLine, transcript_lines
from livetranslator.core.languages import language
from livetranslator.core.store import Store
from livetranslator.theme.icons import app_icon
from livetranslator.theme.qss import settings_qss, transcript_qss, window_qss
from livetranslator.theme.tokens import FONTS, SETTINGS, SPACE, Palette
from livetranslator.ui.session import session_ending
from livetranslator.ui.widgets.chat_line import speaker_color

REDRAW_MS = 200  # batch bursts of partial updates into one redraw
EMPTY = "Nothing has been said yet."
NO_MATCH = "No lines match your search."


def transcript_html(lines: Sequence[TranscriptLine], palette: Palette) -> str:
    """Rich text for the view: speaker heading in its colour, text, indented translations."""
    p = palette
    blocks: list[str] = []
    for line in lines:
        heading = (
            f'<span style="color:{p.text_secondary}">{html.escape(line.offset)}</span> '
            f'<b style="color:{speaker_color(p, line.speaker_key)}">'
            f"{html.escape(line.speaker)}</b>"
        )
        if line.language:
            heading += (
                f' <span style="color:{p.text_secondary}">'
                f"{html.escape(language(line.language).english)}</span>"
            )
        text_color = p.text_primary if line.finished else p.text_secondary
        rows = [heading, f'<span style="color:{text_color}">{html.escape(line.text)}</span>']
        rows += [
            f'<span style="color:{p.text_secondary}">'
            f"{html.escape(language(code).english)}:</span> {html.escape(text)}"
            for code, text in line.translations
        ]
        # Paragraph margins (Qt's rich text ignores most nested <div> spacing): the gap after
        # each line sits on its last paragraph, translations are an indented paragraph.
        gap = f"margin-top:0; margin-bottom:{SPACE.md}px"
        if len(rows) > 2:
            blocks.append(f'<p style="margin:0">{rows[0]}<br>{rows[1]}</p>')
            blocks.append(
                f'<p style="{gap}; margin-left:{SPACE.lg}px">' + "<br>".join(rows[2:]) + "</p>"
            )
        else:
            blocks.append(f'<p style="{gap}">{rows[0]}<br>{rows[1]}</p>')
    return "".join(blocks)


class TranscriptWindow(QWidget):
    def __init__(
        self,
        store: Store,
        palette: Palette,
        export: Callable[[QWidget], Path | None],
        export_error: Callable[[], str] = lambda: "",
        parent: QWidget | None = None,
    ) -> None:
        # Above pinned (always-on-top) overlays, which otherwise covered it (user report
        # 2026-10-18: "Settings doesn't appear").
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self._store = store
        self._palette = palette
        self._export = export
        self._export_error = export_error
        self.setObjectName("TranscriptRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowTitle("Transcript")  # Qt adds " - Live Translator"
        self.setWindowIcon(app_icon())
        self.setStyleSheet(window_qss(palette) + settings_qss(palette) + transcript_qss(palette))
        self.resize(SETTINGS.width, SETTINGS.height)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search what was said")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(SETTINGS.control_width)
        self.count = QLabel(self)
        self.count.setObjectName("SettingsNote")
        self.copy = QPushButton("Copy", self)
        self.copy.setToolTip("Copy every line shown")
        self.export_button = QPushButton("Export…", self)
        self.status = QLabel(self)
        self.status.setObjectName("SettingsNote")
        self.view = QTextBrowser(self)
        self.view.setObjectName("TranscriptView")
        self.view.setOpenLinks(False)
        font = self.view.font()
        font.setPointSize(FONTS.ui_size_large)
        self.view.setFont(font)

        bar = QHBoxLayout()
        bar.setSpacing(SPACE.sm)
        bar.addWidget(self.search)
        bar.addWidget(self.count)
        bar.addStretch(1)
        bar.addWidget(self.copy)
        bar.addWidget(self.export_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE.lg, SPACE.lg, SPACE.lg, SPACE.md)
        layout.setSpacing(SPACE.sm)
        layout.addLayout(bar)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.status)

        self.shown: list[TranscriptLine] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REDRAW_MS)
        self._timer.timeout.connect(self.redraw)
        for signal in (store.utterance_added, store.utterance_updated, store.utterance_removed):
            signal.connect(lambda _id: self.schedule())
        store.session_cleared.connect(self.schedule)
        store.speaker_changed.connect(lambda _id: self.schedule())
        store.config_changed.connect(lambda _section: self.schedule())
        self.search.textChanged.connect(lambda _text: self.redraw())
        self.copy.clicked.connect(self.copy_shown)
        self.export_button.clicked.connect(self._on_export)
        self.redraw()

    def schedule(self) -> None:
        if self.isVisible() and not self._timer.isActive():
            self._timer.start()

    def redraw(self) -> None:
        all_lines = transcript_lines(self._store.state)
        needle = self.search.text()
        self.shown = [line for line in all_lines if line.matches(needle)]
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - SPACE.lg
        if self.shown:
            self.view.setHtml(transcript_html(self.shown, self._palette))
        else:
            message = NO_MATCH if all_lines else EMPTY
            self.view.setHtml(
                f'<p style="color:{self._palette.text_secondary}">{html.escape(message)}</p>'
            )
        if at_bottom:
            bar.setValue(bar.maximum())
        total = len(all_lines)
        shown = len(self.shown)
        self.count.setText(
            f"{total} line{'s' if total != 1 else ''}"
            if shown == total
            else f"{shown} of {total} lines"
        )
        self.copy.setEnabled(bool(self.shown))
        self.export_button.setEnabled(bool(all_lines))

    def copy_shown(self) -> None:
        text = "\n\n".join(line.block() for line in self.shown)
        QGuiApplication.clipboard().setText(text)
        self.status.setText(f"Copied {len(self.shown)} line{'s' if len(self.shown) != 1 else ''}.")

    def _on_export(self) -> None:
        path = self._export(self)
        if path is not None:
            self.status.setText(f"Saved to {path}")
        else:
            self.status.setText(self._export_error())

    def bring_to_front(self) -> None:
        self.redraw()
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if session_ending():
            event.accept()  # Windows is logging off / shutting down: never block it
            return
        event.ignore()  # reused next time
        self.hide()
