"""Target-language dropdown (T022)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QWidget

from livetranslator.core.languages import DEFAULT_LANGUAGES, Language, language


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
        for lang in languages:
            self.addItem(lang.label, lang.code)
        self.set_language(current)
        self.activated.connect(lambda index: self.language_changed.emit(self.itemData(index)))

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
