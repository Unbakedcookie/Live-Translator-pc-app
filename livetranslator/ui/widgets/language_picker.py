"""Target-language dropdown with type-to-search (T022; G1 feedback 2026-10-17).

Languages are listed A-Z by English name. Clicking opens a popup with a search box: typing
filters by English name, native name or code ("ja", "japan", "日本"), Up/Down move, Enter
picks, Esc closes. The widget keeps the QComboBox interface (model, `activated`, `findData`)
so callers and tests don't care that the popup is custom.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QComboBox, QFrame, QLineEdit, QListView, QVBoxLayout, QWidget

from livetranslator.core.languages import DEFAULT_LANGUAGES, Language, language
from livetranslator.theme.tokens import (
    DEFAULT_PALETTE_ID,
    PALETTES,
    RADIUS,
    SPACE,
    WINDOW,
    Palette,
)

MAX_VISIBLE = 12
CODE_ROLE = Qt.ItemDataRole.UserRole


def sorted_languages(languages: Sequence[Language]) -> list[Language]:
    return sorted(languages, key=lambda lang: lang.english.casefold())


class _LanguageFilter(QSortFilterProxyModel):
    """Matches the search text against the label (English + native) and the code."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._needle = ""

    def set_needle(self, text: str) -> None:
        self.beginFilterChange()
        self._needle = text.strip().casefold()
        self.endFilterChange()

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        if not self._needle:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        label = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "").casefold()
        code = str(model.data(index, CODE_ROLE) or "").casefold()
        return self._needle in label or code.startswith(self._needle)


class LanguagePopup(QFrame):
    """Search box + filtered list. A child of the picker, so the window's QSS
    ("QComboBox QAbstractItemView ...") styles the list."""

    def __init__(self, picker: LanguagePicker) -> None:
        super().__init__(
            picker,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._picker = picker
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search languages")
        self.search.setClearButtonEnabled(True)
        self.proxy = _LanguageFilter(self)
        self.proxy.setSourceModel(picker.model())
        self.list = QListView(self)
        self.list.setModel(self.proxy)
        self.list.setUniformItemSizes(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE.xs, SPACE.xs, SPACE.xs, SPACE.xs)
        layout.setSpacing(SPACE.xs)
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        self.search.textChanged.connect(self._on_search)
        self.search.installEventFilter(self)
        self.list.clicked.connect(self._choose)
        self.list.activated.connect(self._choose)

    def open_below(self) -> None:
        picker = self._picker
        self.search.clear()
        self._select_row(
            self.proxy.mapFromSource(picker.model().index(picker.currentIndex(), 0)).row()
        )
        rows = min(MAX_VISIBLE, self.proxy.rowCount())
        row_h = max(self.list.sizeHintForRow(0), WINDOW.chrome_height)
        width = max(self.list.sizeHintForColumn(0) + 2 * SPACE.md + SPACE.lg, picker.width())
        self.list.setFixedSize(width, rows * row_h + 2 * SPACE.sm)
        self.adjustSize()
        self.move(picker.mapToGlobal(QPoint(0, picker.height())))
        self.show()
        self.activateWindow()
        self.search.setFocus()

    def _select_row(self, row: int) -> None:
        if 0 <= row < self.proxy.rowCount():
            index = self.proxy.index(row, 0)
            self.list.setCurrentIndex(index)
            self.list.scrollTo(index)

    def _on_search(self, text: str) -> None:
        self.proxy.set_needle(text)
        self._select_row(0)

    def _choose(self, index: QModelIndex | None = None) -> None:
        index = index if index is not None and index.isValid() else self.list.currentIndex()
        if not index.isValid():
            return
        source_row = self.proxy.mapToSource(index).row()
        self.hide()
        self._picker.setCurrentIndex(source_row)
        self._picker.activated.emit(source_row)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)  # nosec B101 - Qt guarantees the type
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if key == Qt.Key.Key_Down else -1
                self._select_row(self.list.currentIndex().row() + step)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._choose()
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._picker.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(theme.border))
        painter.setBrush(QColor(theme.surface))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()


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
        for lang in sorted_languages(languages):
            self.addItem(lang.label, lang.code)
        self.set_language(current)
        self.activated.connect(lambda index: self.language_changed.emit(self.itemData(index)))
        self.popup: LanguagePopup | None = None
        self.theme: Palette = PALETTES[DEFAULT_PALETTE_ID]

    def apply_palette(self, palette: Palette) -> None:
        """Colours for the popup's own background (the list itself follows the window QSS)."""
        self.theme = palette
        if self.popup is not None:
            self.popup.update()

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

    def showPopup(self) -> None:
        if self.popup is None:
            self.popup = LanguagePopup(self)
        self.popup.open_below()

    def hidePopup(self) -> None:
        if self.popup is not None:
            self.popup.hide()
