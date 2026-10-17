"""Overlay font dropdown (T024; G1 feedback 2026-10-17: match the language dropdown).

Lists the installed font families A-Z in the shared SearchPopup. Families that can write
Latin text are previewed in their own face; symbol and non-Latin fonts are shown in the UI
font so their names stay readable.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QWidget

from livetranslator.ui.widgets.search_combo import SearchCombo


def installed_families() -> list[str]:
    """Selectable families, A-Z: no private (system UI) or vertical ("@...") variants."""
    families = {
        family
        for family in QFontDatabase.families()
        if not family.startswith("@") and not QFontDatabase.isPrivateFamily(family)
    }
    return sorted(families, key=str.casefold)


def _previewable(family: str) -> bool:
    return QFontDatabase.WritingSystem.Latin in QFontDatabase.writingSystems(family)


class FontPicker(SearchCombo):
    font_changed = Signal(str)  # family name
    search_placeholder = "Search fonts"

    def __init__(
        self,
        current: str,
        families: Iterable[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        for family in installed_families() if families is None else families:
            self._add(family)
        self.set_family(current)
        self.activated.connect(lambda index: self.font_changed.emit(self.itemData(index)))

    def _add(self, family: str) -> None:
        self.addItem(family, family)
        if _previewable(family):
            self.setItemData(self.count() - 1, QFont(family), Qt.ItemDataRole.FontRole)

    def current_family(self) -> str:
        return str(self.currentData())

    def set_family(self, family: str) -> None:
        """Select `family` without emitting (adds it if it isn't installed, e.g. a font
        saved on another PC, so the setting is still shown truthfully)."""
        self.select_data(family, family)
