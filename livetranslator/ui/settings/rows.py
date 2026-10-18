"""Building blocks of every Settings page (T072; gate G3): a scrolling page with a title,
sections drawn as cards, and rows of "title + explanation | control".

The wizard and Language Manager (T073/T074) reuse these, so they are a shared component.
Colours and sizes come from `settings_qss` via object names.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from livetranslator.theme.tokens import SETTINGS, SPACE, WINDOW


def number_box(minimum: int, maximum: int, step: int = 1, suffix: str = "") -> QSpinBox:
    """Whole-number box (ms, %, s) that reports a value once typing is finished."""
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    box.setFixedWidth(SETTINGS.number_width)
    return box


def silently(widget: QWidget, update: Callable[[], object]) -> None:
    """Apply a store value to a control without firing its change signals."""
    blocker = QSignalBlocker(widget)
    update()
    blocker.unblock()


def note(text: str, parent: QWidget | None = None, name: str = "SettingsNote") -> QLabel:
    """A small secondary-colour paragraph (wraps)."""
    label = QLabel(text, parent)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return label


class SettingRow(QWidget):
    """Title (+ optional explanation) on the left, the control on the right."""

    def __init__(
        self,
        title: str,
        description: str = "",
        control: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = QLabel(title, self)
        self.description = note(description, self, "SettingsRowDescription")
        self.description.setVisible(bool(description))
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(SPACE.xs // 2)
        text.addWidget(self.title)
        text.addWidget(self.description)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE.lg, SPACE.md, SPACE.lg, SPACE.md)
        layout.setSpacing(SPACE.lg)
        layout.addLayout(text, 1)
        self.control = control
        if control is not None:
            control.setParent(self)
            layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_description(self, text: str) -> None:
        self.description.setText(text)
        self.description.setVisible(bool(text))


class Section(QWidget):
    """A small heading over a card that stacks rows with thin dividers between them."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.sm)
        if title:
            heading = QLabel(title, self)
            heading.setObjectName("SettingsSectionTitle")
            layout.addWidget(heading)
        self.card = QFrame(self)
        self.card.setObjectName("SettingsCard")
        self._rows = QVBoxLayout(self.card)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)
        layout.addWidget(self.card)

    def add(self, widget: QWidget) -> QWidget:
        if self._rows.count():
            divider = QFrame(self.card)
            divider.setObjectName("SettingsDivider")
            divider.setFixedHeight(WINDOW.border_width)
            self._rows.addWidget(divider)
        widget.setParent(self.card)
        self._rows.addWidget(widget)
        return widget

    def row(self, title: str, description: str = "", control: QWidget | None = None) -> SettingRow:
        row = SettingRow(title, description, control)
        self.add(row)
        return row


class SettingsPage(QScrollArea):
    """One page: big title, optional intro, then sections. Scrolls when it's taller than
    the window."""

    title_text = ""
    icon_name = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(self)
        body.setObjectName("SettingsPageBody")
        body.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # a click on empty space ends edits
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(SPACE.xl, SPACE.xl, SPACE.xl, SPACE.xl)
        self.body.setSpacing(SPACE.xl)
        title = QLabel(self.title_text, body)
        title.setObjectName("SettingsPageTitle")
        self.body.addWidget(title)
        self.setWidget(body)

    def intro(self, text: str) -> QLabel:
        label = note(text)
        self.body.addWidget(label)
        return label

    def section(self, title: str = "") -> Section:
        section = Section(title)
        self.body.addWidget(section)
        return section

    def finish(self) -> None:
        """Call after adding everything: keeps sections at the top of a tall window."""
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.body.addWidget(spacer, 1)

    def refresh(self) -> None:
        """Re-read the store into the controls (without emitting). Pages override."""
