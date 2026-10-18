"""Dropdown for a short fixed list (T072): the shared SearchCombo popup without the search box,
so every dropdown in the app looks the same (G1 feedback: "keep the app uniform")."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from livetranslator.ui.widgets.search_combo import SearchCombo


class ChoiceCombo(SearchCombo):
    choice_changed = Signal(object)  # the chosen item's data
    searchable = False

    def __init__(
        self,
        items: Sequence[tuple[str, object]],
        current: object = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.set_items(items, current)
        self.activated.connect(lambda index: self.choice_changed.emit(self.itemData(index)))

    def set_items(self, items: Sequence[tuple[str, object]], current: object = None) -> None:
        """Replace the list (e.g. devices plugged in or out) without emitting."""
        self.blockSignals(True)
        self.clear()
        for label, data in items:
            self.addItem(label, data)
        self.blockSignals(False)
        self.set_choice(current)

    def set_choice(self, data: object) -> None:
        """Select the item holding `data` without emitting (first item if there is none)."""
        index = next((i for i in range(self.count()) if self.itemData(i) == data), 0)
        self.blockSignals(True)
        self.setCurrentIndex(index)
        self.blockSignals(False)

    def current_choice(self) -> object:
        return self.currentData()
