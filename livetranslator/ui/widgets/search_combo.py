"""Dropdown with a type-to-search popup (T022; G1 feedback 2026-10-17).

The one dropdown style of the app: languages and fonts both use it. Clicking opens a
rounded popup with a search box over the list: typing filters by label (or by the item's
data as a prefix, e.g. a language code), Up/Down move, Enter picks, Esc closes. The widget
keeps the QComboBox interface (model, `activated`, `findData`) so callers and tests don't
care that the popup is custom. Short fixed lists (ChoiceCombo, T072) use the same popup
without the search box.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QComboBox, QFrame, QLineEdit, QListView, QVBoxLayout, QWidget

from livetranslator.theme.tokens import (
    DEFAULT_PALETTE_ID,
    PALETTES,
    RADIUS,
    SPACE,
    WINDOW,
    Palette,
)

MAX_VISIBLE = 12
DATA_ROLE = Qt.ItemDataRole.UserRole


class _SearchFilter(QSortFilterProxyModel):
    """Matches the search text inside the label, or as a prefix of the item data."""

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
        data = str(model.data(index, DATA_ROLE) or "").casefold()
        return self._needle in label or data.startswith(self._needle)


class SearchPopup(QFrame):
    """Search box + filtered list. A child of the combo, so the window's QSS
    ("QComboBox QAbstractItemView ...") styles the list."""

    def __init__(self, combo: SearchCombo) -> None:
        super().__init__(
            combo,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._combo = combo
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(combo.search_placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.setVisible(combo.searchable)
        self.proxy = _SearchFilter(self)
        self.proxy.setSourceModel(combo.model())
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
        self.list.installEventFilter(self)
        self.list.clicked.connect(self._choose)
        self.list.activated.connect(self._choose)

    def open_below(self) -> None:
        combo = self._combo
        self.search.clear()
        rows = min(MAX_VISIBLE, self.proxy.rowCount())
        row_h = max(self.list.sizeHintForRow(0), WINDOW.chrome_height)
        width = max(self.list.sizeHintForColumn(0) + 2 * SPACE.md + SPACE.lg, combo.width())
        self.list.setFixedSize(width, rows * row_h + 2 * SPACE.sm)
        self.adjustSize()
        self.move(combo.mapToGlobal(QPoint(0, combo.height())))
        self.show()
        # Scroll to the current item only now that the list has its full height: before, it
        # scrolled the top rows out of view ("Detect any language" hidden; user 2026-10-20).
        self.list.scrollToTop()
        self._select_row(
            self.proxy.mapFromSource(combo.model().index(combo.currentIndex(), 0)).row()
        )
        self.activateWindow()
        (self.search if self._combo.searchable else self.list).setFocus()

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
        self._combo.setCurrentIndex(source_row)
        self._combo.activated.emit(source_row)

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
        if watched is self.list and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)  # nosec B101 - Qt guarantees the type
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._combo.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(theme.border))
        painter.setBrush(QColor(theme.surface))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()


class SearchCombo(QComboBox):
    """A QComboBox whose popup is the SearchPopup. Subclasses fill the items."""

    search_placeholder = "Search"
    searchable = True

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.popup: SearchPopup | None = None
        self.theme: Palette = PALETTES[DEFAULT_PALETTE_ID]

    def apply_palette(self, palette: Palette) -> None:
        """Colours for the popup's own background (the list itself follows the window QSS)."""
        self.theme = palette
        if self.popup is not None:
            self.popup.update()

    def select_data(self, data: str, label: str) -> None:
        """Select the item holding `data` without emitting (added as `label` if missing)."""
        index = self.findData(data)
        if index < 0:
            self.addItem(label, data)
            index = self.count() - 1
        self.blockSignals(True)
        self.setCurrentIndex(index)
        self.blockSignals(False)

    def showPopup(self) -> None:
        if self.popup is None:
            self.popup = SearchPopup(self)
        self.popup.open_below()

    def hidePopup(self) -> None:
        if self.popup is not None:
            self.popup.hide()
