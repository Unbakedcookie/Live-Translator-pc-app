"""Target-language dropdown (T022)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QListView, QWidget

from livetranslator.core.languages import DEFAULT_LANGUAGES, Language, language
from livetranslator.theme.tokens import SPACE

MAX_VISIBLE = 12


class LanguagePicker(QComboBox):
    language_changed = Signal(str)  # ISO code

    def __init__(
        self,
        current: str,
        languages: Sequence[Language] = DEFAULT_LANGUAGES,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.setMaxVisibleItems(MAX_VISIBLE)
        # A QListView makes the QSS ::item rules (row height, padding, hover) apply; the
        # default view's delegate ignores them. Frameless + translucent popup container so
        # the list's rounded corners show instead of a square native frame and shadow.
        self.setView(QListView(self))
        popup = self.view().window()
        popup.setWindowFlags(
            popup.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        for lang in languages:
            self.addItem(lang.label, lang.code)
        self.set_language(current)
        self.activated.connect(lambda index: self.language_changed.emit(self.itemData(index)))

    def showPopup(self) -> None:
        # Size the list to its widest entry (+ row padding and scrollbar) so long names like
        # "Portuguese · Português" aren't cut off in a narrow chrome strip.
        view = self.view()
        widest = view.sizeHintForColumn(0) + 2 * SPACE.md + SPACE.sm + SPACE.lg
        view.setMinimumWidth(max(widest, self.width()))
        super().showPopup()

    def current_code(self) -> str:
        return str(self.currentData())

    def set_language(self, code: str) -> None:
        """Select `code` without emitting (adds an entry if it isn't in the list)."""
        index = self.findData(code)
        if index < 0:
            self.addItem(language(code).label, code)
            index = self.count() - 1
        self.blockSignals(True)
        self.setCurrentIndex(index)
        self.blockSignals(False)
