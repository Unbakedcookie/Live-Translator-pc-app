"""Target-language dropdown (T022; G1 feedback 2026-10-17).

Languages are listed A-Z by English name. The popup is the shared SearchPopup: typing
filters by English name, native name or code ("ja", "japan", "日本").
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from livetranslator.core.languages import DEFAULT_LANGUAGES, Language, language
from livetranslator.ui.widgets.search_combo import SearchCombo


def sorted_languages(languages: Sequence[Language]) -> list[Language]:
    return sorted(languages, key=lambda lang: lang.english.casefold())


class LanguagePicker(SearchCombo):
    language_changed = Signal(str)  # ISO code
    search_placeholder = "Search languages"

    def __init__(
        self,
        current: str,
        languages: Sequence[Language] = DEFAULT_LANGUAGES,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        for lang in sorted_languages(languages):
            self.addItem(lang.label, lang.code)
        self.set_language(current)
        self.activated.connect(lambda index: self.language_changed.emit(self.itemData(index)))

    def current_code(self) -> str:
        return str(self.currentData())

    def set_language(self, code: str) -> None:
        """Select `code` without emitting (adds an entry if it isn't in the list)."""
        self.select_data(code, language(code).label)
